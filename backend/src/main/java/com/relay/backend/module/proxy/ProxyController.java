package com.relay.backend.module.proxy;

import com.relay.backend.common.error.AppException;
import com.relay.backend.common.error.ErrorCode;
import com.relay.backend.common.web.ClientIpResolver;
import com.relay.backend.module.apikey.ApiKeyService;
import com.relay.backend.module.log.ProxyRequestLogContext;
import com.relay.backend.module.log.RequestLogService;
import com.relay.backend.module.user.UserRepository;
import jakarta.servlet.http.HttpServletRequest;
import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import javax.net.ssl.SSLSession;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.util.StreamUtils;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

@RestController
public class ProxyController {

  private static final Logger log = LoggerFactory.getLogger(ProxyController.class);
  private static final int LOG_RESPONSE_CAPTURE_LIMIT = 256 * 1024;
  private static final Duration CODEX_SSE_HEARTBEAT_INTERVAL = Duration.ofSeconds(2);
  private static final String CODEX_SSE_HEARTBEAT = ": relay-keepalive\n\n";
  private static final String CODEX_UPSTREAM_ORIGINATOR = "codex_cli_rs";
  private static final String CODEX_UPSTREAM_USER_AGENT = "codex_cli_rs/0.126.0 (Windows 10; x86_64)";
  private static final String CODEX_UPSTREAM_VERSION = "0.126.0";
  private static final Set<String> REQUEST_HEADERS_TO_DROP =
      Set.of(
          "accept-encoding",
          "content-length",
          "host",
          "authorization",
          "connection",
          "keep-alive",
          "proxy-authenticate",
          "proxy-authorization",
          "te",
          "trailer",
          "transfer-encoding",
          "upgrade");
  private static final Set<String> RESPONSE_HEADERS_TO_DROP =
      Set.of(
          "connection",
          "content-encoding",
          "content-length",
          "keep-alive",
          "proxy-authenticate",
          "proxy-authorization",
          "te",
          "trailer",
          "transfer-encoding",
          "upgrade");

  private final ApiKeyService apiKeyService;
  private final ClientTypeDetector clientTypeDetector;
  private final CodexRequestCaptureService codexRequestCaptureService;
  private final UpstreamRouter upstreamRouter;
  private final RequestLogService requestLogService;
  private final UserRepository userRepository;
  private final ClientIpResolver clientIpResolver;
  private final ObjectMapper objectMapper;
  private final HttpClient httpClient =
      HttpClient.newBuilder()
          .connectTimeout(Duration.ofSeconds(30))
          .version(HttpClient.Version.HTTP_1_1)
          .build();

  public ProxyController(
      ApiKeyService apiKeyService,
      ClientTypeDetector clientTypeDetector,
      CodexRequestCaptureService codexRequestCaptureService,
      UpstreamRouter upstreamRouter,
      RequestLogService requestLogService,
      UserRepository userRepository,
      ClientIpResolver clientIpResolver,
      ObjectMapper objectMapper) {
    this.apiKeyService = apiKeyService;
    this.clientTypeDetector = clientTypeDetector;
    this.codexRequestCaptureService = codexRequestCaptureService;
    this.upstreamRouter = upstreamRouter;
    this.requestLogService = requestLogService;
    this.userRepository = userRepository;
    this.clientIpResolver = clientIpResolver;
    this.objectMapper = objectMapper;
  }

  @RequestMapping({"/v1/**", "/backend-api/codex/**"})
  public ResponseEntity<StreamingResponseBody> proxy(HttpServletRequest request) throws IOException {
    byte[] body = StreamUtils.copyToByteArray(request.getInputStream());
    boolean eventStream = acceptsEventStream(request);
    ProxyRequestSnapshot requestSnapshot = ProxyRequestSnapshot.from(request);
    String clientIp = clientIpResolver.resolve(request);
    String userAgent = request.getHeader("User-Agent");
    String requestMethod = request.getMethod();
    String requestUri = request.getRequestURI();
    String queryString = request.getQueryString();
    ClientType clientType = clientTypeDetector.detect(request, body);
    codexRequestCaptureService.capture(request, body, clientType);

    com.relay.backend.module.apikey.ApiKeyRecord apiKey;
    try {
      apiKey = apiKeyService.authenticateRawKey(extractBearer(request.getHeader(HttpHeaders.AUTHORIZATION)));
    } catch (AppException exception) {
      return localErrorResponse(HttpStatus.UNAUTHORIZED, "Invalid API key", eventStream);
    } catch (Exception exception) {
      log.warn("Unable to authenticate proxy API key", exception);
      return localErrorResponse(
          HttpStatus.SERVICE_UNAVAILABLE, "Relay authentication service is unavailable", eventStream);
    }
    if (hasInsufficientBalance(apiKey.userId())) {
      return localErrorResponse(HttpStatus.PAYMENT_REQUIRED, "余额不足", eventStream);
    }

    UpstreamLease lease;
    try {
      lease = upstreamRouter.acquire(clientType);
    } catch (AppException exception) {
      return localErrorResponse(exception.status(), exception.getMessage(), eventStream);
    } catch (Exception exception) {
      log.warn("Unable to acquire upstream service", exception);
      return localErrorResponse(
          HttpStatus.SERVICE_UNAVAILABLE, "Relay upstream router is unavailable", eventStream);
    }

    Instant startedAt = Instant.now();
    if (clientType == ClientType.CODEX && eventStream) {
      return toLazyCodexStreamingResponse(
          apiKey,
          clientType,
          body,
          requestSnapshot,
          lease,
          startedAt,
          clientIp,
          userAgent,
          request.getHeader("x-client-request-id"),
          requestMethod,
          requestUri,
          queryString);
    }

    Set<Long> quotaFailedServiceIds = new HashSet<>();
    while (true) {
      if (clientType == ClientType.CODEX && lease.config().usesCodexProfileRequest()
          && lease.config().codexProfile() == null) {
        safeClose(lease);
        return localErrorResponse(
            HttpStatus.SERVICE_UNAVAILABLE,
            "Codex profile request mode requires an openai_codex_profiles row",
            eventStream);
      }

      byte[] upstreamBody = normalizeUpstreamBody(body, lease.config(), clientType, eventStream);
      HttpRequest upstreamRequest;
      try {
        upstreamRequest = buildUpstreamRequest(requestSnapshot, upstreamBody, lease.config(), clientType);
      } catch (AppException exception) {
        safeClose(lease);
        return localErrorResponse(exception.status(), exception.getMessage(), eventStream);
      }

      HttpResponse<InputStream> upstreamResponse;
      try {
        upstreamResponse = httpClient.send(upstreamRequest, HttpResponse.BodyHandlers.ofInputStream());
      } catch (InterruptedException exception) {
        Thread.currentThread().interrupt();
        safeClose(lease);
        return localErrorResponse(HttpStatus.BAD_GATEWAY, "Upstream request interrupted", eventStream);
      } catch (Exception exception) {
        safeClose(lease);
        return localErrorResponse(HttpStatus.BAD_GATEWAY, "Unable to reach upstream service", eventStream);
      }

      if (shouldInspectQuotaRetry(clientType, lease.config(), upstreamResponse.statusCode())) {
        byte[] upstreamResponseBody;
        try {
          upstreamResponseBody = readAndCloseResponseBody(upstreamResponse);
        } catch (IOException exception) {
          safeClose(lease);
          return localErrorResponse(HttpStatus.BAD_GATEWAY, "Unable to read upstream error response", eventStream);
        }
        if (UpstreamQuotaErrorDetector.isRetryableQuotaError(upstreamResponse.statusCode(), upstreamResponseBody)) {
          quotaFailedServiceIds.add(lease.config().id());
          UpstreamLease nextLease = acquireReplacementLease(clientType, quotaFailedServiceIds);
          if (nextLease != null) {
            log.warn(
                "upstream_quota_retry requestId={} failedUpstreamServiceId={} nextUpstreamServiceId={} status={}",
                request.getHeader("x-client-request-id"),
                lease.config().id(),
                nextLease.config().id(),
                upstreamResponse.statusCode());
            UpstreamLease failedLease = lease;
            lease = nextLease;
            safeClose(failedLease);
            continue;
          }
        }
        upstreamResponse = bufferedResponse(upstreamResponse, upstreamResponseBody);
      }

      return toStreamingResponse(
          apiKey,
          clientType,
          body,
          upstreamResponse,
          lease,
          startedAt,
          lease.config().id(),
          clientIp,
          userAgent,
          request.getHeader("x-client-request-id"),
          requestMethod,
          requestUri,
          queryString);
    }
  }

  private HttpRequest buildUpstreamRequest(
      ProxyRequestSnapshot request, byte[] body, UpstreamConfig upstream, ClientType clientType) {
    String targetUrl = joinUrl(upstreamApiEndpoint(upstream), request.requestUri(), request.queryString());
    HttpRequest.Builder builder = HttpRequest.newBuilder(URI.create(targetUrl)).timeout(Duration.ofMinutes(10));

    if (clientType == ClientType.CODEX) {
      applyStableCodexHeaders(builder, request, body);
      if (upstream.usesCodexProfileRequest()) {
        applyCodexProfileAuthHeaders(builder, upstream.codexProfile());
      } else {
        builder.header(HttpHeaders.AUTHORIZATION, "Bearer " + upstream.token());
      }
    } else {
      request.headers()
          .forEach(
              (name, values) -> {
                if (shouldForwardHeader(name)) {
                  values.forEach(value -> builder.header(name, value));
                }
              });
      builder.header(HttpHeaders.AUTHORIZATION, "Bearer " + upstream.token());
    }

    builder.method(request.method(), requestBodyPublisher(request.method(), body));
    return builder.build();
  }

  private boolean hasInsufficientBalance(java.util.UUID userId) {
    return userRepository
        .findById(userId)
        .map(user -> (user.balance() == null ? BigDecimal.ZERO : user.balance()).compareTo(BigDecimal.ZERO) < 0)
        .orElse(true);
  }

  private String upstreamApiEndpoint(UpstreamConfig upstream) {
    if (upstream.usesCodexProfileRequest() && upstream.codexProfile() != null) {
      return firstNonBlank(upstream.codexProfile().baseUrl(), upstream.apiEndpoint());
    }
    return upstream.apiEndpoint();
  }

  private void applyCodexProfileAuthHeaders(HttpRequest.Builder builder, CodexProfileConfig profile) {
    String accessToken = firstNonBlank(profile.accessToken(), profile.openAiApiKey());
    if (accessToken == null || accessToken.isBlank()) {
      throw new AppException(
          ErrorCode.VALIDATION_FAILED,
          "Codex profile request mode requires access_token or openai_api_key",
          HttpStatus.SERVICE_UNAVAILABLE);
    }
    builder.setHeader(HttpHeaders.AUTHORIZATION, "Bearer " + cleanBearerToken(accessToken));
    if (profile.accountId() != null && !profile.accountId().isBlank()) {
      builder.setHeader("ChatGPT-Account-ID", profile.accountId().trim());
    }
  }

  private void applyStableCodexHeaders(HttpRequest.Builder builder, ProxyRequestSnapshot request, byte[] body) {
    String accept = request.firstHeader(HttpHeaders.ACCEPT);
    if (accept == null || accept.isBlank() || isStreamRequest(body)) {
      builder.setHeader(HttpHeaders.ACCEPT, "text/event-stream");
    } else {
      builder.setHeader(HttpHeaders.ACCEPT, accept);
    }
    builder.setHeader(HttpHeaders.CONTENT_TYPE, "application/json");
    builder.setHeader("originator", CODEX_UPSTREAM_ORIGINATOR);
    builder.setHeader("user-agent", CODEX_UPSTREAM_USER_AGENT);
    builder.setHeader("version", CODEX_UPSTREAM_VERSION);
  }

  private boolean isStreamRequest(byte[] body) {
    if (body == null || body.length == 0) {
      return false;
    }
    return new String(body, java.nio.charset.StandardCharsets.UTF_8).contains("\"stream\":true");
  }

  private byte[] normalizeUpstreamBody(
      byte[] body, UpstreamConfig upstream, ClientType clientType, boolean eventStream) {
    if (clientType != ClientType.CODEX || body == null || body.length == 0) {
      return body;
    }

    try {
      JsonNode root = objectMapper.readTree(body);
      if (!(root instanceof ObjectNode rootObject)) {
        return body;
      }
      if (upstream.usesCodexProfileRequest()) {
        applyCodexProfileBodyDefaults(rootObject, upstream.codexProfile());
      }
      if (eventStream) {
        rootObject.put("stream", true);
      }
      if (isChatGptCodexEndpoint(upstreamApiEndpoint(upstream))) {
        rootObject.remove("truncation");
      }
      return objectMapper.writeValueAsBytes(rootObject);
    } catch (Exception exception) {
      log.warn("Unable to normalize Codex upstream body; forwarding original body", exception);
      return body;
    }
  }

  private boolean isChatGptCodexEndpoint(String apiEndpoint) {
    return apiEndpoint != null
        && apiEndpoint.toLowerCase(Locale.ROOT).contains("chatgpt.com/backend-api/codex");
  }

  private void applyCodexProfileBodyDefaults(ObjectNode rootObject, CodexProfileConfig profile) {
    if (profile == null) {
      return;
    }
    putTextIfMissing(rootObject, "model", profile.model());
    if (!rootObject.has("store")) {
      rootObject.put("store", false);
    }
    if (!rootObject.has("parallel_tool_calls")) {
      rootObject.put("parallel_tool_calls", true);
    }

    JsonNode reasoningEffort = rootObject.remove("reasoning_effort");
    if (!rootObject.has("reasoning")) {
      String effort = firstNonBlank(
          reasoningEffort == null ? null : reasoningEffort.asText(),
          profile.reasoningEffort());
      if (effort != null && !effort.isBlank()) {
        ObjectNode reasoning = objectMapper.createObjectNode();
        reasoning.put("effort", effort);
        rootObject.set("reasoning", reasoning);
      }
    }
  }

  private void putTextIfMissing(ObjectNode rootObject, String fieldName, String value) {
    if (value == null || value.isBlank()) {
      return;
    }
    JsonNode existing = rootObject.get(fieldName);
    if (existing == null || existing.isNull() || existing.asText().isBlank()) {
      rootObject.put(fieldName, value);
    }
  }

  private String firstNonBlank(String first, String second) {
    if (first != null && !first.isBlank()) {
      return first.trim();
    }
    if (second != null && !second.isBlank()) {
      return second.trim();
    }
    return null;
  }

  private String cleanBearerToken(String token) {
    String cleaned = token.trim();
    return cleaned.toLowerCase(Locale.ROOT).startsWith("bearer ")
        ? cleaned.substring("bearer ".length()).trim()
        : cleaned;
  }

  private HttpRequest.BodyPublisher requestBodyPublisher(String method, byte[] body) {
    if (body.length == 0 && ("GET".equalsIgnoreCase(method) || "DELETE".equalsIgnoreCase(method))) {
      return HttpRequest.BodyPublishers.noBody();
    }
    return HttpRequest.BodyPublishers.ofByteArray(body);
  }

  private ResponseEntity<StreamingResponseBody> toStreamingResponse(
      com.relay.backend.module.apikey.ApiKeyRecord apiKey,
      ClientType clientType,
      byte[] requestBody,
      HttpResponse<InputStream> upstreamResponse,
      UpstreamLease lease,
      Instant startedAt,
      Long upstreamServiceId,
      String clientIp,
      String userAgent,
      String clientRequestId,
      String requestMethod,
      String requestUri,
      String queryString) {
    HttpHeaders headers = new HttpHeaders();
    upstreamResponse
        .headers()
        .map()
        .forEach(
            (name, values) -> {
              if (shouldReturnHeader(name)) {
                headers.put(name, values);
              }
            });
    headers.set(HttpHeaders.CACHE_CONTROL, "no-cache");
    headers.set("X-Accel-Buffering", "no");

    StreamingResponseBody stream =
        outputStream -> {
          ByteArrayOutputStream responseBuffer = new ByteArrayOutputStream(8192);
          long firstTokenMs = 0L;
          long responseBytes = 0L;
          boolean sawFirstChunk = false;
          Exception streamException = null;
          log.info(
              "proxy_stream_start requestId={} clientType={} uri={} upstreamStatus={} upstreamServiceId={}",
              clientRequestId,
              clientType,
              requestUri,
              upstreamResponse.statusCode(),
              upstreamServiceId);
          try (lease; java.io.InputStream inputStream = upstreamResponse.body()) {
            StreamCopyResult result =
                clientType == ClientType.CODEX && isEventStream(upstreamResponse)
                    ? streamCodexSse(inputStream, outputStream, responseBuffer, startedAt, false)
                    : streamBytes(inputStream, outputStream, responseBuffer, startedAt);
            responseBytes = result.responseBytes();
            sawFirstChunk = result.sawFirstChunk();
            firstTokenMs = result.firstTokenMs();
          } catch (Exception exception) {
            streamException = exception;
            // The stream may end because the client disconnected or the upstream closed early.
            // At this point the response is already text/event-stream, so do not route it
            // through the JSON exception handler.
          } finally {
            long useTimeMs = Duration.between(startedAt, Instant.now()).toMillis();
            log.info(
                "proxy_stream_end requestId={} clientType={} uri={} status={} bytes={} firstTokenMs={} useTimeMs={} completed={} error={}",
                clientRequestId,
                clientType,
                requestUri,
                upstreamResponse.statusCode(),
                responseBytes,
                sawFirstChunk ? firstTokenMs : useTimeMs,
                useTimeMs,
                containsResponseCompleted(responseBuffer),
                streamException == null ? null : streamException.getClass().getSimpleName());
            try {
              requestLogService.recordProxyRequestAsync(
                  new ProxyRequestLogContext(
                      apiKey,
                      clientType,
                      requestMethod,
                      requestUri,
                      queryString,
                      clientIp,
                      userAgent,
                      requestBody,
                      responseBuffer.toByteArray(),
                      upstreamServiceId,
                      upstreamResponse.headers().map(),
                      upstreamResponse.statusCode(),
                      useTimeMs,
                      sawFirstChunk ? firstTokenMs : useTimeMs));
            } catch (Exception ignored) {
              // Logging should never break proxying.
            }
          }
        };

    return new ResponseEntity<>(stream, headers, HttpStatus.valueOf(upstreamResponse.statusCode()));
  }

  private ResponseEntity<StreamingResponseBody> toLazyCodexStreamingResponse(
      com.relay.backend.module.apikey.ApiKeyRecord apiKey,
      ClientType clientType,
      byte[] requestBody,
      ProxyRequestSnapshot requestSnapshot,
      UpstreamLease lease,
      Instant startedAt,
      String clientIp,
      String userAgent,
      String clientRequestId,
      String requestMethod,
      String requestUri,
      String queryString) {
    HttpHeaders headers = new HttpHeaders();
    headers.set(HttpHeaders.CONTENT_TYPE, "text/event-stream; charset=utf-8");
    headers.set(HttpHeaders.CACHE_CONTROL, "no-cache");
    headers.set("X-Accel-Buffering", "no");

    StreamingResponseBody stream =
        outputStream -> {
          ByteArrayOutputStream responseBuffer = new ByteArrayOutputStream(8192);
          long firstTokenMs = 0L;
          long responseBytes = 0L;
          boolean sawFirstChunk = false;
          Integer upstreamStatus = null;
          String upstreamContentType = null;
          Exception streamException = null;
          HttpResponse<InputStream> upstreamResponse = null;
          UpstreamLease activeLease = lease;
          Long activeUpstreamServiceId = activeLease.config().id();
          Set<Long> quotaFailedServiceIds = new HashSet<>();
          log.info(
              "proxy_stream_start requestId={} clientType={} uri={} upstreamStatus=pending upstreamServiceId={}",
              clientRequestId,
              clientType,
              requestUri,
              activeUpstreamServiceId);
          try {
            StreamCopyResult initialHeartbeat = writeCodexHeartbeat(outputStream, responseBuffer, startedAt);
            responseBytes += initialHeartbeat.responseBytes();
            firstTokenMs = initialHeartbeat.firstTokenMs();
            sawFirstChunk = initialHeartbeat.sawFirstChunk();

            while (true) {
              activeUpstreamServiceId = activeLease.config().id();
              if (clientType == ClientType.CODEX && activeLease.config().usesCodexProfileRequest()
                  && activeLease.config().codexProfile() == null) {
                throw new AppException(
                    ErrorCode.VALIDATION_FAILED,
                    "Codex profile request mode requires an openai_codex_profiles row",
                    HttpStatus.SERVICE_UNAVAILABLE);
              }
              byte[] upstreamBody = normalizeUpstreamBody(requestBody, activeLease.config(), clientType, true);
              HttpRequest upstreamRequest =
                  buildUpstreamRequest(requestSnapshot, upstreamBody, activeLease.config(), clientType);
              upstreamResponse = httpClient.send(upstreamRequest, HttpResponse.BodyHandlers.ofInputStream());
              upstreamStatus = upstreamResponse.statusCode();
              upstreamContentType = upstreamResponse.headers().firstValue(HttpHeaders.CONTENT_TYPE).orElse(null);

              if (shouldInspectQuotaRetry(clientType, activeLease.config(), upstreamStatus)) {
                byte[] upstreamResponseBody = readAndCloseResponseBody(upstreamResponse);
                if (UpstreamQuotaErrorDetector.isRetryableQuotaError(upstreamStatus, upstreamResponseBody)) {
                  quotaFailedServiceIds.add(activeLease.config().id());
                  UpstreamLease nextLease = acquireReplacementLease(clientType, quotaFailedServiceIds);
                  if (nextLease != null) {
                    log.warn(
                        "upstream_quota_retry requestId={} failedUpstreamServiceId={} nextUpstreamServiceId={} status={}",
                        clientRequestId,
                        activeLease.config().id(),
                        nextLease.config().id(),
                        upstreamStatus);
                    UpstreamLease failedLease = activeLease;
                    activeLease = nextLease;
                    safeClose(failedLease);
                    upstreamResponse = null;
                    upstreamStatus = null;
                    continue;
                  }
                }

                StreamCopyResult result =
                    streamCodexUpstreamError(
                        new ByteArrayInputStream(upstreamResponseBody),
                        outputStream,
                        responseBuffer,
                        startedAt,
                        upstreamStatus);
                responseBytes += result.responseBytes();
                if (!sawFirstChunk && result.sawFirstChunk()) {
                  firstTokenMs = result.firstTokenMs();
                }
                sawFirstChunk = sawFirstChunk || result.sawFirstChunk();
                safeClose(activeLease);
                activeLease = null;
                break;
              }

              try (InputStream inputStream = upstreamResponse.body()) {
                StreamCopyResult result =
                    isSuccessfulStatus(upstreamStatus)
                        ? streamCodexSse(
                            inputStream,
                            outputStream,
                            responseBuffer,
                            startedAt,
                            activeLease.config().usesCodexProfileRequest())
                        : streamCodexUpstreamError(
                            inputStream, outputStream, responseBuffer, startedAt, upstreamStatus);
                responseBytes += result.responseBytes();
                if (!sawFirstChunk && result.sawFirstChunk()) {
                  firstTokenMs = result.firstTokenMs();
                }
                sawFirstChunk = sawFirstChunk || result.sawFirstChunk();
              }
              safeClose(activeLease);
              activeLease = null;
              break;
            }
          } catch (AppException exception) {
            streamException = exception;
            writeCodexSseError(outputStream, responseBuffer, exception.getMessage());
          } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            streamException = exception;
            writeCodexSseError(outputStream, responseBuffer, "Upstream request interrupted");
          } catch (Exception exception) {
            streamException = exception;
            if (!isClientDisconnect(exception)) {
              writeCodexSseError(outputStream, responseBuffer, "Unable to reach upstream service");
            }
          } finally {
            if (activeLease != null) {
              safeClose(activeLease);
            }
            long useTimeMs = Duration.between(startedAt, Instant.now()).toMillis();
            int statusCode = upstreamStatus == null ? HttpStatus.BAD_GATEWAY.value() : upstreamStatus;
            log.info(
                "proxy_stream_end requestId={} clientType={} uri={} status={} bytes={} firstTokenMs={} useTimeMs={} completed={} upstreamContentType={} error={}",
                clientRequestId,
                clientType,
                requestUri,
                statusCode,
                responseBytes,
                sawFirstChunk ? firstTokenMs : useTimeMs,
                useTimeMs,
                containsResponseCompleted(responseBuffer),
                upstreamContentType,
                streamException == null ? null : streamException.getClass().getSimpleName());
            try {
              requestLogService.recordProxyRequestAsync(
                  new ProxyRequestLogContext(
                      apiKey,
                      clientType,
                      requestMethod,
                      requestUri,
                      queryString,
                      clientIp,
                      userAgent,
                      requestBody,
                      responseBuffer.toByteArray(),
                      activeUpstreamServiceId,
                      upstreamResponse == null ? Map.of() : upstreamResponse.headers().map(),
                      statusCode,
                      useTimeMs,
                      sawFirstChunk ? firstTokenMs : useTimeMs));
            } catch (Exception ignored) {
              // Logging should never break proxying.
            }
          }
        };

    return new ResponseEntity<>(stream, headers, HttpStatus.OK);
  }

  private boolean shouldInspectQuotaRetry(ClientType clientType, UpstreamConfig upstream, int statusCode) {
    return clientType == ClientType.CODEX
        && upstream.usesCodexProfileRequest()
        && UpstreamQuotaErrorDetector.isRetryableStatus(statusCode);
  }

  private boolean isSuccessfulStatus(int statusCode) {
    return statusCode >= 200 && statusCode < 300;
  }

  private UpstreamLease acquireReplacementLease(ClientType clientType, Set<Long> excludedServiceIds) {
    try {
      return upstreamRouter.acquire(clientType, excludedServiceIds);
    } catch (AppException exception) {
      log.info("No replacement upstream service is available after quota error: {}", exception.getMessage());
      return null;
    } catch (Exception exception) {
      log.warn("Unable to acquire replacement upstream service after quota error", exception);
      return null;
    }
  }

  private byte[] readAndCloseResponseBody(HttpResponse<InputStream> response) throws IOException {
    try (InputStream inputStream = response.body()) {
      return StreamUtils.copyToByteArray(inputStream);
    }
  }

  private HttpResponse<InputStream> bufferedResponse(HttpResponse<InputStream> response, byte[] body) {
    return new BufferedHttpResponse(response, body);
  }

  private String extractBearer(String authorization) {
    String prefix = "Bearer ";
    if (authorization == null || !authorization.startsWith(prefix)) {
      throw new AppException(ErrorCode.UNAUTHORIZED, "Missing API key", HttpStatus.UNAUTHORIZED);
    }
    return authorization.substring(prefix.length());
  }

  private ResponseEntity<StreamingResponseBody> localErrorResponse(
      HttpStatus status, String message, boolean eventStream) {
    HttpHeaders headers = new HttpHeaders();
    headers.set(HttpHeaders.CACHE_CONTROL, "no-cache");
    headers.set("X-Accel-Buffering", "no");
    String body =
        "{\"error\":{\"message\":\""
            + jsonEscape(message)
            + "\",\"type\":\"relay_error\",\"code\":\"relay_error\"}}";
    byte[] bytes = (eventStream ? "event: error\ndata: " + body + "\n\n" : body).getBytes(StandardCharsets.UTF_8);
    headers.set(HttpHeaders.CONTENT_TYPE, eventStream ? "text/event-stream; charset=utf-8" : "application/json");
    return new ResponseEntity<>(outputStream -> outputStream.write(bytes), headers, status);
  }

  private boolean acceptsEventStream(HttpServletRequest request) {
    String accept = request.getHeader(HttpHeaders.ACCEPT);
    return accept != null && accept.contains("text/event-stream");
  }

  private String jsonEscape(String value) {
    if (value == null) {
      return "";
    }
    return value.replace("\\", "\\\\").replace("\"", "\\\"");
  }

  private String joinUrl(String baseUrl, String path, String query) {
    String normalizedBase = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
    String suffix = path;
    if (path.startsWith("/v1")) {
      suffix = path.substring("/v1".length());
    } else if (path.startsWith("/backend-api/codex")) {
      suffix = path.substring("/backend-api/codex".length());
    }
    String target = normalizedBase + (suffix.isBlank() ? "" : suffix);
    return query == null || query.isBlank() ? target : target + "?" + query;
  }

  private boolean shouldForwardHeader(String name) {
    String lower = name.toLowerCase(Locale.ROOT);
    return !REQUEST_HEADERS_TO_DROP.contains(lower);
  }

  private boolean shouldReturnHeader(String name) {
    String lower = name.toLowerCase(Locale.ROOT);
    return !RESPONSE_HEADERS_TO_DROP.contains(lower);
  }

  private void captureForLog(ByteArrayOutputStream responseBuffer, byte[] buffer, int read) {
    int remaining = LOG_RESPONSE_CAPTURE_LIMIT - responseBuffer.size();
    if (remaining <= 0) {
      return;
    }
    responseBuffer.write(buffer, 0, Math.min(read, remaining));
  }

  private StreamCopyResult streamBytes(
      InputStream inputStream,
      OutputStream outputStream,
      ByteArrayOutputStream responseBuffer,
      Instant startedAt)
      throws IOException {
    long responseBytes = 0L;
    long firstTokenMs = 0L;
    boolean sawFirstChunk = false;
    byte[] buffer = new byte[8192];
    int read;
    while ((read = inputStream.read(buffer)) != -1) {
      outputStream.write(buffer, 0, read);
      outputStream.flush();
      responseBytes += read;
      captureForLog(responseBuffer, buffer, read);
      if (!sawFirstChunk) {
        sawFirstChunk = true;
        firstTokenMs = Duration.between(startedAt, Instant.now()).toMillis();
      }
    }
    return new StreamCopyResult(responseBytes, firstTokenMs, sawFirstChunk);
  }

  private StreamCopyResult streamCodexSse(
      InputStream inputStream,
      OutputStream outputStream,
      ByteArrayOutputStream responseBuffer,
      Instant startedAt,
      boolean preserveOutbound)
      throws IOException {
    long responseBytes = 0L;
    long firstTokenMs = 0L;
    boolean sawFirstChunk = false;

    BlockingQueue<SseReadResult> queue = new LinkedBlockingQueue<>();
    ExecutorService readerExecutor =
        Executors.newSingleThreadExecutor(
            runnable -> {
              Thread thread = new Thread(runnable, "codex-sse-reader");
              thread.setDaemon(true);
              return thread;
            });
    Future<?> readerTask =
        readerExecutor.submit(
            () -> {
              try (BufferedReader reader =
                  new BufferedReader(new InputStreamReader(inputStream, StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                  queue.put(new SseReadResult(line, false, null));
                }
                queue.put(new SseReadResult(null, true, null));
              } catch (Exception exception) {
                queue.offer(new SseReadResult(null, false, exception));
              }
            });

    try {
      while (true) {
        SseReadResult result;
        try {
          result = queue.poll(CODEX_SSE_HEARTBEAT_INTERVAL.toMillis(), TimeUnit.MILLISECONDS);
        } catch (InterruptedException exception) {
          Thread.currentThread().interrupt();
          throw new IOException("Interrupted while waiting for upstream SSE", exception);
        }

        String outboundLine;
        String captureLine;
        if (result == null) {
          outboundLine = CODEX_SSE_HEARTBEAT;
          captureLine = CODEX_SSE_HEARTBEAT;
        } else if (result.error() != null) {
          throw new IOException("Unable to read upstream SSE", result.error());
        } else if (result.endOfStream()) {
          break;
        } else {
          captureLine = sanitizeCodexSseLine(result.line()) + "\n";
          outboundLine = preserveOutbound ? result.line() + "\n" : captureLine;
        }

        byte[] bytes = outboundLine.getBytes(StandardCharsets.UTF_8);
        outputStream.write(bytes);
        outputStream.flush();
        responseBytes += bytes.length;
        byte[] captureBytes = captureLine.getBytes(StandardCharsets.UTF_8);
        captureForLog(responseBuffer, captureBytes, captureBytes.length);
        if (!sawFirstChunk) {
          sawFirstChunk = true;
          firstTokenMs = Duration.between(startedAt, Instant.now()).toMillis();
        }
      }
    } finally {
      readerTask.cancel(true);
      readerExecutor.shutdownNow();
      inputStream.close();
    }
    return new StreamCopyResult(responseBytes, firstTokenMs, sawFirstChunk);
  }

  private StreamCopyResult streamCodexUpstreamError(
      InputStream inputStream,
      OutputStream outputStream,
      ByteArrayOutputStream responseBuffer,
      Instant startedAt,
      int upstreamStatus)
      throws IOException {
    String upstreamBody = new String(StreamUtils.copyToByteArray(inputStream), StandardCharsets.UTF_8);
    String message = "Upstream returned HTTP " + upstreamStatus;
    if (!upstreamBody.isBlank()) {
      message += ": " + truncate(upstreamBody, 2000);
    }
    byte[] bytes = codexSseErrorBytes(message);
    outputStream.write(bytes);
    outputStream.flush();
    captureForLog(responseBuffer, bytes, bytes.length);
    return new StreamCopyResult(
        bytes.length, Duration.between(startedAt, Instant.now()).toMillis(), true);
  }

  private StreamCopyResult writeCodexHeartbeat(
      OutputStream outputStream, ByteArrayOutputStream responseBuffer, Instant startedAt)
      throws IOException {
    byte[] heartbeat = CODEX_SSE_HEARTBEAT.getBytes(StandardCharsets.UTF_8);
    outputStream.write(heartbeat);
    outputStream.flush();
    captureForLog(responseBuffer, heartbeat, heartbeat.length);
    return new StreamCopyResult(
        heartbeat.length, Duration.between(startedAt, Instant.now()).toMillis(), true);
  }

  private void writeCodexSseError(
      OutputStream outputStream, ByteArrayOutputStream responseBuffer, String message) {
    try {
      byte[] bytes = codexSseErrorBytes(message);
      outputStream.write(bytes);
      outputStream.flush();
      captureForLog(responseBuffer, bytes, bytes.length);
    } catch (Exception ignored) {
      // The client may already be gone.
    }
  }

  private byte[] codexSseErrorBytes(String message) {
    String body =
        "event: error\ndata: {\"error\":{\"message\":\""
            + jsonEscape(message)
            + "\",\"type\":\"relay_error\",\"code\":\"relay_error\"}}\n\n";
    return body.getBytes(StandardCharsets.UTF_8);
  }

  private String truncate(String value, int maxLength) {
    return value.length() <= maxLength ? value : value.substring(0, maxLength) + "...";
  }

  private String sanitizeCodexSseLine(String line) {
    if (!line.startsWith("data:")) {
      return line;
    }

    String payload = line.substring(5).trim();
    if (payload.isEmpty() || "[DONE]".equals(payload)) {
      return line;
    }

    try {
      JsonNode root = objectMapper.readTree(payload);
      if (!(root instanceof ObjectNode rootObject)) {
        return line;
      }
      JsonNode response = rootObject.get("response");
      if (response instanceof ObjectNode responseObject) {
        responseObject.remove(List.of("instructions", "tools", "input"));
        return "data: " + objectMapper.writeValueAsString(rootObject);
      }
      return line;
    } catch (Exception ignored) {
      return line;
    }
  }

  private boolean isEventStream(HttpResponse<InputStream> upstreamResponse) {
    return upstreamResponse.headers().firstValue(HttpHeaders.CONTENT_TYPE)
        .map(value -> value.toLowerCase(Locale.ROOT).contains("text/event-stream"))
        .orElse(false);
  }

  private boolean containsResponseCompleted(ByteArrayOutputStream responseBuffer) {
    return responseBuffer.toString(StandardCharsets.UTF_8).contains("\"response.completed\"");
  }

  private boolean isClientDisconnect(Exception exception) {
    String name = exception.getClass().getSimpleName();
    String message = exception.getMessage();
    return "AsyncRequestNotUsableException".equals(name)
        || "ClientAbortException".equals(name)
        || (message != null && message.toLowerCase(Locale.ROOT).contains("broken pipe"));
  }

  private void safeClose(UpstreamLease lease) {
    try {
      lease.close();
    } catch (Exception exception) {
      log.warn("Unable to release upstream lease", exception);
    }
  }

  private record ProxyRequestSnapshot(
      String method, String requestUri, String queryString, Map<String, List<String>> headers) {

    static ProxyRequestSnapshot from(HttpServletRequest request) {
      Map<String, List<String>> headers = new LinkedHashMap<>();
      var headerNames = request.getHeaderNames();
      if (headerNames != null) {
        Collections.list(headerNames)
            .forEach(name -> headers.put(name, Collections.list(request.getHeaders(name))));
      }
      return new ProxyRequestSnapshot(
          request.getMethod(), request.getRequestURI(), request.getQueryString(), headers);
    }

    String firstHeader(String headerName) {
      for (Map.Entry<String, List<String>> entry : headers.entrySet()) {
        if (entry.getKey().equalsIgnoreCase(headerName) && !entry.getValue().isEmpty()) {
          return entry.getValue().get(0);
        }
      }
      return null;
    }
  }

  private record BufferedHttpResponse(HttpResponse<InputStream> delegate, byte[] bufferedBody)
      implements HttpResponse<InputStream> {

    @Override
    public int statusCode() {
      return delegate.statusCode();
    }

    @Override
    public HttpRequest request() {
      return delegate.request();
    }

    @Override
    public Optional<HttpResponse<InputStream>> previousResponse() {
      return delegate.previousResponse();
    }

    @Override
    public java.net.http.HttpHeaders headers() {
      return delegate.headers();
    }

    @Override
    public InputStream body() {
      return new ByteArrayInputStream(bufferedBody);
    }

    @Override
    public Optional<SSLSession> sslSession() {
      return delegate.sslSession();
    }

    @Override
    public URI uri() {
      return delegate.uri();
    }

    @Override
    public HttpClient.Version version() {
      return delegate.version();
    }
  }

  private record StreamCopyResult(long responseBytes, long firstTokenMs, boolean sawFirstChunk) {}

  private record SseReadResult(String line, boolean endOfStream, Exception error) {}
}
