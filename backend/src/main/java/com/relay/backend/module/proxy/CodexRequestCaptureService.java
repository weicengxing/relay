package com.relay.backend.module.proxy;

import jakarta.servlet.http.HttpServletRequest;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.Executor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import tools.jackson.databind.ObjectMapper;

@Service
public class CodexRequestCaptureService {

  private static final Logger log = LoggerFactory.getLogger(CodexRequestCaptureService.class);
  private static final DateTimeFormatter FILE_TIME_FORMATTER =
      DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss-SSS").withZone(ZoneId.systemDefault());
  private static final List<String> CURL_HEADERS_TO_DROP =
      List.of("connection", "content-length", "host", "transfer-encoding");

  private final ObjectMapper objectMapper;
  private final Executor requestLogExecutor;

  public CodexRequestCaptureService(
      ObjectMapper objectMapper, @Qualifier("requestLogExecutor") Executor requestLogExecutor) {
    this.objectMapper = objectMapper;
    this.requestLogExecutor = requestLogExecutor;
  }

  public void capture(HttpServletRequest request, byte[] body, ClientType clientType) {
    if (clientType != ClientType.CODEX) {
      return;
    }

    Map<String, List<String>> headers = collectHeaders(request);
    CapturedRequest captured =
        new CapturedRequest(
            Instant.now(),
            request.getMethod(),
            fullUrl(request),
            request.getRequestURI(),
            request.getQueryString(),
            clientType.name(),
            headers,
            new String(body, StandardCharsets.UTF_8));
    requestLogExecutor.execute(() -> capture(captured));
  }

  private void capture(CapturedRequest captured) {
    try {
      Path directory = captureDirectory();
      Files.createDirectories(directory);

      String filePrefix =
          FILE_TIME_FORMATTER.format(captured.capturedAt())
              + "-"
              + sanitizePath(captured.path());
      Path latestRequest = directory.resolve("latest-request.json");
      Path latestBody = directory.resolve("latest-body.json");
      Path latestCurl = directory.resolve("latest-curl.ps1");
      Path timestampedRequest = directory.resolve(filePrefix + ".request.json");
      Path timestampedBody = directory.resolve(filePrefix + ".body.json");
      Path timestampedCurl = directory.resolve(filePrefix + ".curl.ps1");

      CapturedRequestDocument document =
          new CapturedRequestDocument(
              captured.capturedAt(),
              captured.method(),
              captured.url(),
              captured.path(),
              captured.query(),
              captured.clientType(),
              captured.headers(),
              "latest-body.json",
              captured.body());

      byte[] requestJson = objectMapper.writerWithDefaultPrettyPrinter().writeValueAsBytes(document);
      byte[] bodyBytes = captured.body().getBytes(StandardCharsets.UTF_8);
      byte[] curlBytes = buildCurlScript(captured, latestBody.toAbsolutePath()).getBytes(StandardCharsets.UTF_8);

      Files.write(latestRequest, requestJson);
      Files.write(latestBody, bodyBytes);
      Files.write(latestCurl, curlBytes);
      Files.write(timestampedRequest, requestJson);
      Files.write(timestampedBody, bodyBytes);
      Files.write(timestampedCurl, buildCurlScript(captured, timestampedBody.toAbsolutePath()).getBytes(StandardCharsets.UTF_8));
    } catch (Exception exception) {
      log.warn("Unable to capture Codex request", exception);
    }
  }

  private Map<String, List<String>> collectHeaders(HttpServletRequest request) {
    Map<String, List<String>> headers = new LinkedHashMap<>();
    request
        .getHeaderNames()
        .asIterator()
        .forEachRemaining(
            name -> {
              List<String> values = new ArrayList<>();
              request.getHeaders(name).asIterator().forEachRemaining(values::add);
              headers.put(name, List.copyOf(values));
            });
    return headers;
  }

  private String fullUrl(HttpServletRequest request) {
    StringBuilder url = new StringBuilder(request.getRequestURL());
    if (request.getQueryString() != null && !request.getQueryString().isBlank()) {
      url.append('?').append(request.getQueryString());
    }
    return url.toString();
  }

  private Path captureDirectory() {
    Path cwd = Path.of("").toAbsolutePath().normalize();
    Path backendDirectory =
        "backend".equalsIgnoreCase(cwd.getFileName().toString()) ? cwd : cwd.resolve("backend");
    return backendDirectory.resolve("captures").resolve("codex");
  }

  private String buildCurlScript(CapturedRequest captured, Path bodyPath) throws IOException {
    StringBuilder script = new StringBuilder();
    script.append("$bodyPath = '").append(powerShellSingleQuote(bodyPath.toString())).append("'\n");
    script.append("curl.exe -N '")
        .append(powerShellSingleQuote(captured.url()))
        .append("' `\n");
    for (Map.Entry<String, List<String>> entry : captured.headers().entrySet()) {
      if (shouldDropCurlHeader(entry.getKey())) {
        continue;
      }
      for (String value : entry.getValue()) {
        script
            .append("  -H '")
            .append(powerShellSingleQuote(entry.getKey()))
            .append(": ")
            .append(powerShellSingleQuote(value))
            .append("' `\n");
      }
    }
    script.append("  --data-binary \"@$bodyPath\"\n");
    return script.toString();
  }

  private boolean shouldDropCurlHeader(String name) {
    return CURL_HEADERS_TO_DROP.contains(name.toLowerCase(Locale.ROOT));
  }

  private String powerShellSingleQuote(String value) {
    return value.replace("'", "''");
  }

  private String sanitizePath(String path) {
    String sanitized = path.replaceAll("[^A-Za-z0-9._-]+", "-").replaceAll("(^-+|-+$)", "");
    if (sanitized.isBlank()) {
      return "request";
    }
    return sanitized.length() > 80 ? sanitized.substring(0, 80) : sanitized;
  }

  private record CapturedRequest(
      Instant capturedAt,
      String method,
      String url,
      String path,
      String query,
      String clientType,
      Map<String, List<String>> headers,
      String body) {}

  private record CapturedRequestDocument(
      Instant capturedAt,
      String method,
      String url,
      String path,
      String query,
      String clientType,
      Map<String, List<String>> headers,
      String bodyFile,
      String body) {}
}
