package com.relay.backend.module.proxy;

import com.relay.backend.common.error.AppException;
import com.relay.backend.common.error.ErrorCode;
import com.relay.backend.common.web.ClientIpResolver;
import com.relay.backend.module.apikey.ApiKeyService;
import com.relay.backend.module.log.ProxyRequestLogContext;
import com.relay.backend.module.log.RequestLogService;
import jakarta.servlet.http.HttpServletRequest;
import java.io.IOException;
import java.io.ByteArrayOutputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;
import java.util.Locale;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.util.StreamUtils;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProxyController {

  private final ApiKeyService apiKeyService;
  private final ClientTypeDetector clientTypeDetector;
  private final UpstreamRouter upstreamRouter;
  private final RequestLogService requestLogService;
  private final ClientIpResolver clientIpResolver;
  private final HttpClient httpClient =
      HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(30)).build();

  public ProxyController(
      ApiKeyService apiKeyService,
      ClientTypeDetector clientTypeDetector,
      UpstreamRouter upstreamRouter,
      RequestLogService requestLogService,
      ClientIpResolver clientIpResolver) {
    this.apiKeyService = apiKeyService;
    this.clientTypeDetector = clientTypeDetector;
    this.upstreamRouter = upstreamRouter;
    this.requestLogService = requestLogService;
    this.clientIpResolver = clientIpResolver;
  }

  @RequestMapping({"/v1/**", "/backend-api/codex/**"})
  public ResponseEntity<StreamingResponseBody> proxy(HttpServletRequest request)
      throws IOException, InterruptedException {
    byte[] body = StreamUtils.copyToByteArray(request.getInputStream());
    var apiKey = apiKeyService.authenticateRawKey(extractBearer(request.getHeader(HttpHeaders.AUTHORIZATION)));
    String clientIp = clientIpResolver.resolve(request);
    String userAgent = request.getHeader("User-Agent");
    String requestMethod = request.getMethod();
    String requestUri = request.getRequestURI();
    String queryString = request.getQueryString();

    ClientType clientType = clientTypeDetector.detect(request, body);
    UpstreamLease lease = upstreamRouter.acquire(clientType);
    HttpRequest upstreamRequest = buildUpstreamRequest(request, body, lease.config());
    Instant startedAt = Instant.now();
    HttpResponse<java.io.InputStream> upstreamResponse =
        httpClient.send(upstreamRequest, HttpResponse.BodyHandlers.ofInputStream());
    return toStreamingResponse(
        apiKey,
        clientType,
        body,
        upstreamResponse,
        lease,
        startedAt,
        clientIp,
        userAgent,
        requestMethod,
        requestUri,
        queryString);
  }

  private HttpRequest buildUpstreamRequest(
      HttpServletRequest request, byte[] body, UpstreamConfig upstream) {
    String targetUrl = joinUrl(upstream.apiEndpoint(), request.getRequestURI(), request.getQueryString());
    HttpRequest.Builder builder = HttpRequest.newBuilder(URI.create(targetUrl)).timeout(Duration.ofMinutes(10));

    request
        .getHeaderNames()
        .asIterator()
        .forEachRemaining(
            name -> {
              if (shouldForwardHeader(name)) {
                request.getHeaders(name).asIterator().forEachRemaining(value -> builder.header(name, value));
              }
            });

    builder.header(HttpHeaders.AUTHORIZATION, "Bearer " + upstream.token());
    builder.method(request.getMethod(), requestBodyPublisher(request.getMethod(), body));
    return builder.build();
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
      HttpResponse<java.io.InputStream> upstreamResponse,
      UpstreamLease lease,
      Instant startedAt,
      String clientIp,
      String userAgent,
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

    StreamingResponseBody stream =
        outputStream -> {
          ByteArrayOutputStream responseBuffer = new ByteArrayOutputStream();
          long firstTokenMs = 0L;
          boolean sawFirstChunk = false;
          boolean completed = false;
          try (lease; java.io.InputStream inputStream = upstreamResponse.body()) {
            byte[] buffer = new byte[8192];
            int read;
            while ((read = inputStream.read(buffer)) != -1) {
              outputStream.write(buffer, 0, read);
              outputStream.flush();
              responseBuffer.write(buffer, 0, read);
              if (!sawFirstChunk) {
                sawFirstChunk = true;
                firstTokenMs = Duration.between(startedAt, Instant.now()).toMillis();
              }
            }
            completed = true;
          } finally {
            long useTimeMs = Duration.between(startedAt, Instant.now()).toMillis();
            try {
              requestLogService.recordProxyRequest(
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
                      upstreamResponse.headers().map(),
                      completed ? upstreamResponse.statusCode() : HttpStatus.BAD_GATEWAY.value(),
                      useTimeMs,
                      sawFirstChunk ? firstTokenMs : useTimeMs));
            } catch (Exception ignored) {
              // Logging should never break proxying.
            }
          }
        };

    return new ResponseEntity<>(stream, headers, HttpStatus.valueOf(upstreamResponse.statusCode()));
  }

  private String extractBearer(String authorization) {
    String prefix = "Bearer ";
    if (authorization == null || !authorization.startsWith(prefix)) {
      throw new AppException(ErrorCode.UNAUTHORIZED, "Missing API key", HttpStatus.UNAUTHORIZED);
    }
    return authorization.substring(prefix.length());
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
    return !lower.equals("host")
        && !lower.equals("content-length")
        && !lower.equals("authorization")
        && !lower.equals("connection")
        && !lower.equals("accept-encoding");
  }

  private boolean shouldReturnHeader(String name) {
    String lower = name.toLowerCase(Locale.ROOT);
    return !lower.equals("transfer-encoding")
        && !lower.equals("connection")
        && !lower.equals("content-length")
        && !lower.equals("content-encoding");
  }
}
