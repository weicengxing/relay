package com.relay.backend.module.log;

import com.relay.backend.module.apikey.ApiKeyRecord;
import com.relay.backend.module.log.dto.RequestLogResponse;
import com.relay.backend.module.proxy.ModelCatalogItem;
import com.relay.backend.module.proxy.ModelCatalogRepository;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class RequestLogService {

  private static final Logger log = LoggerFactory.getLogger(RequestLogService.class);
  private static final BigDecimal MILLION = BigDecimal.valueOf(1_000_000L);
  private static final Pattern MODEL_PATTERN = Pattern.compile("\"model\"\\s*:\\s*\"([^\"]+)\"");
  private static final Pattern NAME_PATTERN = Pattern.compile("\"name\"\\s*:\\s*\"([^\"]+)\"");
  private static final Pattern PROMPT_TOKENS_PATTERN = Pattern.compile("\"prompt_tokens\"\\s*:\\s*(\\d+)");
  private static final Pattern INPUT_TOKENS_PATTERN = Pattern.compile("\"input_tokens\"\\s*:\\s*(\\d+)");
  private static final Pattern INPUT_TOKENS_CAMEL_PATTERN = Pattern.compile("\"inputTokens\"\\s*:\\s*(\\d+)");
  private static final Pattern COMPLETION_TOKENS_PATTERN =
      Pattern.compile("\"completion_tokens\"\\s*:\\s*(\\d+)");
  private static final Pattern OUTPUT_TOKENS_PATTERN = Pattern.compile("\"output_tokens\"\\s*:\\s*(\\d+)");
  private static final Pattern OUTPUT_TOKENS_CAMEL_PATTERN = Pattern.compile("\"outputTokens\"\\s*:\\s*(\\d+)");
  private static final Pattern CACHE_READ_PATTERN = Pattern.compile("\"cache_read_input_tokens\"\\s*:\\s*(\\d+)");
  private static final Pattern CACHE_READ_ALT_PATTERN = Pattern.compile("\"cached_tokens\"\\s*:\\s*(\\d+)");
  private static final Pattern CACHE_READ_SIMPLE_PATTERN = Pattern.compile("\"cache_read_tokens\"\\s*:\\s*(\\d+)");
  private static final Pattern CACHE_CREATE_PATTERN =
      Pattern.compile("\"cache_creation_input_tokens\"\\s*:\\s*(\\d+)");
  private static final Pattern CACHE_CREATE_ALT_PATTERN =
      Pattern.compile("\"cache_creation_tokens\"\\s*:\\s*(\\d+)");

  private final RequestLogRepository requestLogRepository;
  private final ModelCatalogRepository modelCatalogRepository;

  public RequestLogService(
      RequestLogRepository requestLogRepository,
      ModelCatalogRepository modelCatalogRepository) {
    this.requestLogRepository = requestLogRepository;
    this.modelCatalogRepository = modelCatalogRepository;
  }

  @Async("requestLogExecutor")
  public void recordProxyRequestAsync(ProxyRequestLogContext context) {
    try {
      ParsedUsage usage = parseUsage(context);
      ModelCatalogItem price = findPrice(usage.model());
      BigDecimal cost = calculateCost(usage, price);

      requestLogRepository.save(
          new RequestLogRecord(
              null,
              context.apiKey().userId(),
              context.apiKey().id(),
              displayToken(context.apiKey()),
              displayGroup(context.apiKey()),
              "usage",
              context.clientType().name(),
              usage.model(),
              safeInt(context.useTimeMs()),
              safeInt(context.firstTokenMs()),
              usage.inputTokens(),
              usage.outputTokens(),
              usage.cacheReadTokens(),
              usage.cacheCreationTokens(),
              cost,
              emptyToNull(context.clientIp()),
              statusLabel(context.statusCode()),
              context.upstreamServiceId(),
              UpstreamResponseDetailCodec.encode(context.responseBody()),
              Instant.now()));
    } catch (Exception exception) {
      log.warn("Unable to write request log", exception);
    }
  }

  public List<RequestLogResponse> list(UUID userId, int limit) {
    return requestLogRepository.findRecentByUserId(userId, limit).stream()
        .map(this::toResponse)
        .toList();
  }

  private RequestLogResponse toResponse(RequestLogRecord record) {
    return new RequestLogResponse(
        record.id(),
        record.createdAt(),
        record.tokenName(),
        record.groupKey(),
        record.requestType(),
        record.model(),
        record.useTimeMs(),
        record.firstTokenMs(),
        record.promptTokens(),
        record.completionTokens(),
        record.cacheReadTokens(),
        record.cacheCreationTokens(),
        record.cost(),
        record.ip(),
        record.status(),
        record.upstreamServiceId(),
        splitDetail(record.detail()));
  }

  private ParsedUsage parseUsage(ProxyRequestLogContext context) {
    String requestText = normalizeText(context.requestBody());
    String responseText = normalizeText(context.responseBody());

    String model =
        firstText(
            extractText(responseText, MODEL_PATTERN),
            extractText(requestText, MODEL_PATTERN),
            extractText(requestText, NAME_PATTERN));

    int inputTokens =
        firstInt(
            extractInt(responseText, PROMPT_TOKENS_PATTERN),
            extractInt(responseText, INPUT_TOKENS_PATTERN),
            extractInt(responseText, INPUT_TOKENS_CAMEL_PATTERN),
            extractInt(requestText, PROMPT_TOKENS_PATTERN),
            extractInt(requestText, INPUT_TOKENS_PATTERN),
            extractInt(requestText, INPUT_TOKENS_CAMEL_PATTERN));
    int outputTokens =
        firstInt(
            extractInt(responseText, COMPLETION_TOKENS_PATTERN),
            extractInt(responseText, OUTPUT_TOKENS_PATTERN),
            extractInt(responseText, OUTPUT_TOKENS_CAMEL_PATTERN),
            extractInt(requestText, COMPLETION_TOKENS_PATTERN),
            extractInt(requestText, OUTPUT_TOKENS_PATTERN),
            extractInt(requestText, OUTPUT_TOKENS_CAMEL_PATTERN));
    int cacheReadTokens =
        firstInt(
            extractInt(responseText, CACHE_READ_PATTERN),
            extractInt(responseText, CACHE_READ_ALT_PATTERN),
            extractInt(responseText, CACHE_READ_SIMPLE_PATTERN),
            extractInt(requestText, CACHE_READ_PATTERN),
            extractInt(requestText, CACHE_READ_ALT_PATTERN),
            extractInt(requestText, CACHE_READ_SIMPLE_PATTERN));
    int cacheCreationTokens =
        firstInt(
            extractInt(responseText, CACHE_CREATE_PATTERN),
            extractInt(responseText, CACHE_CREATE_ALT_PATTERN),
            extractInt(requestText, CACHE_CREATE_PATTERN),
            extractInt(requestText, CACHE_CREATE_ALT_PATTERN));

    return new ParsedUsage(model, inputTokens, outputTokens, cacheReadTokens, cacheCreationTokens);
  }

  private String normalizeText(byte[] body) {
    if (body == null || body.length == 0) {
      return null;
    }
    String text = new String(body, StandardCharsets.UTF_8).trim();
    if (text.isEmpty()) {
      return null;
    }

    String ssePayload = extractSsePayload(text);
    return ssePayload == null ? text : ssePayload;
  }

  private String extractSsePayload(String text) {
    String lastJson = null;
    for (String block : text.split("\\R\\R+")) {
      for (String line : block.split("\\R")) {
        String trimmed = line.trim();
        if (!trimmed.startsWith("data:")) {
          continue;
        }
        String payload = trimmed.substring(5).trim();
        if (!payload.isEmpty() && !"[DONE]".equals(payload)) {
          lastJson = payload;
        }
      }
    }
    return lastJson;
  }

  private String extractText(String text, Pattern pattern) {
    if (text == null || text.isBlank()) {
      return null;
    }
    Matcher matcher = pattern.matcher(text);
    if (!matcher.find()) {
      return null;
    }
    String value = matcher.group(1);
    return value == null || value.isBlank() ? null : value;
  }

  private Integer extractInt(String text, Pattern pattern) {
    if (text == null || text.isBlank()) {
      return null;
    }
    Matcher matcher = pattern.matcher(text);
    if (!matcher.find()) {
      return null;
    }
    try {
      return Math.max(0, Integer.parseInt(matcher.group(1)));
    } catch (NumberFormatException ignored) {
      return null;
    }
  }

  private String firstText(String... values) {
    for (String value : values) {
      if (value != null && !value.isBlank()) {
        return value;
      }
    }
    return null;
  }

  private int firstInt(Integer... values) {
    for (Integer value : values) {
      if (value != null) {
        return value;
      }
    }
    return 0;
  }

  private ModelCatalogItem findPrice(String model) {
    if (model == null || model.isBlank()) {
      return null;
    }
    return modelCatalogRepository.findById(model).orElse(null);
  }

  private BigDecimal calculateCost(ParsedUsage usage, ModelCatalogItem price) {
    if (price == null) {
      return BigDecimal.ZERO.setScale(6, RoundingMode.HALF_UP);
    }

    BigDecimal cost =
        price.inputPrice().multiply(BigDecimal.valueOf(usage.inputTokens()))
            .add(price.outputPrice().multiply(BigDecimal.valueOf(usage.outputTokens())))
            .add(price.cachedInputPrice().multiply(BigDecimal.valueOf(usage.cacheReadTokens())))
            .add(price.cacheCreationPrice().multiply(BigDecimal.valueOf(usage.cacheCreationTokens())))
            .divide(MILLION, 6, RoundingMode.HALF_UP);
    return cost.setScale(6, RoundingMode.HALF_UP);
  }

  private List<String> splitDetail(String detail) {
    String decoded = UpstreamResponseDetailCodec.decode(detail);
    if (decoded == null || decoded.isBlank()) {
      return List.of();
    }
    return decoded.lines().toList();
  }

  private String displayToken(ApiKeyRecord apiKey) {
    if (apiKey.name() != null && !apiKey.name().isBlank()) {
      return apiKey.name();
    }
    return displayKey(apiKey.keyHash());
  }

  private String displayGroup(ApiKeyRecord apiKey) {
    if (apiKey.keyValue() != null && !apiKey.keyValue().isBlank()) {
      return apiKey.keyValue();
    }
    return displayKey(apiKey.keyHash());
  }

  private String displayKey(String keyHash) {
    return "relay_" + keyHash.substring(0, Math.min(8, keyHash.length())) + "...";
  }

  private String statusLabel(int statusCode) {
    return statusCode >= 200 && statusCode < 300 ? "success" : "error";
  }

  private String emptyToNull(String value) {
    return value == null || value.isBlank() ? null : value;
  }

  private int safeInt(long value) {
    if (value > Integer.MAX_VALUE) {
      return Integer.MAX_VALUE;
    }
    if (value < Integer.MIN_VALUE) {
      return Integer.MIN_VALUE;
    }
    return (int) value;
  }

  private record ParsedUsage(
      String model,
      int inputTokens,
      int outputTokens,
      int cacheReadTokens,
      int cacheCreationTokens) {}
}
