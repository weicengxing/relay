package com.relay.backend.module.log;

import com.relay.backend.module.apikey.ApiKeyRecord;
import com.relay.backend.module.log.dto.RequestLogResponse;
import com.relay.backend.module.proxy.ModelCatalogItem;
import com.relay.backend.module.proxy.ModelCatalogRepository;
import com.relay.backend.module.user.BalanceUpdatePublisher;
import com.relay.backend.module.user.UserRepository;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

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
  private final UserRepository userRepository;
  private final BalanceUpdatePublisher balanceUpdatePublisher;
  private final BillingSettingsRepository billingSettingsRepository;
  private final ObjectMapper objectMapper;

  public RequestLogService(
      RequestLogRepository requestLogRepository,
      ModelCatalogRepository modelCatalogRepository,
      UserRepository userRepository,
      BalanceUpdatePublisher balanceUpdatePublisher,
      BillingSettingsRepository billingSettingsRepository,
      ObjectMapper objectMapper) {
    this.requestLogRepository = requestLogRepository;
    this.modelCatalogRepository = modelCatalogRepository;
    this.userRepository = userRepository;
    this.balanceUpdatePublisher = balanceUpdatePublisher;
    this.billingSettingsRepository = billingSettingsRepository;
    this.objectMapper = objectMapper;
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
      if (cost.signum() > 0) {
        BigDecimal balance = userRepository.deductBalance(context.apiKey().userId(), cost);
        balanceUpdatePublisher.publish(context.apiKey().userId(), balance);
      }
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
    UsageFields responseUsage = extractStructuredUsage(context.responseBody());
    UsageFields requestUsage = extractStructuredUsage(context.requestBody());

    String model =
        firstText(
            responseUsage.model(),
            extractText(responseText, MODEL_PATTERN),
            requestUsage.model(),
            extractText(requestText, MODEL_PATTERN),
            extractText(requestText, NAME_PATTERN));

    int inputTokens =
        firstInt(
            responseUsage.inputTokens(),
            extractInt(responseText, PROMPT_TOKENS_PATTERN),
            extractInt(responseText, INPUT_TOKENS_PATTERN),
            extractInt(responseText, INPUT_TOKENS_CAMEL_PATTERN),
            requestUsage.inputTokens(),
            extractInt(requestText, PROMPT_TOKENS_PATTERN),
            extractInt(requestText, INPUT_TOKENS_PATTERN),
            extractInt(requestText, INPUT_TOKENS_CAMEL_PATTERN));
    int outputTokens =
        firstInt(
            responseUsage.outputTokens(),
            extractInt(responseText, COMPLETION_TOKENS_PATTERN),
            extractInt(responseText, OUTPUT_TOKENS_PATTERN),
            extractInt(responseText, OUTPUT_TOKENS_CAMEL_PATTERN),
            requestUsage.outputTokens(),
            extractInt(requestText, COMPLETION_TOKENS_PATTERN),
            extractInt(requestText, OUTPUT_TOKENS_PATTERN),
            extractInt(requestText, OUTPUT_TOKENS_CAMEL_PATTERN));
    int cacheReadTokens =
        firstInt(
            responseUsage.cacheReadTokens(),
            extractInt(responseText, CACHE_READ_PATTERN),
            extractInt(responseText, CACHE_READ_ALT_PATTERN),
            extractInt(responseText, CACHE_READ_SIMPLE_PATTERN),
            requestUsage.cacheReadTokens(),
            extractInt(requestText, CACHE_READ_PATTERN),
            extractInt(requestText, CACHE_READ_ALT_PATTERN),
            extractInt(requestText, CACHE_READ_SIMPLE_PATTERN));
    int cacheCreationTokens =
        firstInt(
            responseUsage.cacheCreationTokens(),
            extractInt(responseText, CACHE_CREATE_PATTERN),
            extractInt(responseText, CACHE_CREATE_ALT_PATTERN),
            requestUsage.cacheCreationTokens(),
            extractInt(requestText, CACHE_CREATE_PATTERN),
            extractInt(requestText, CACHE_CREATE_ALT_PATTERN));

    if (inputTokens == 0 && cacheReadTokens > 0) {
      inputTokens = cacheReadTokens;
    }

    return new ParsedUsage(model, inputTokens, outputTokens, cacheReadTokens, cacheCreationTokens);
  }

  private UsageFields extractStructuredUsage(byte[] body) {
    if (body == null || body.length == 0) {
      return UsageFields.empty();
    }
    String text = new String(body, StandardCharsets.UTF_8).trim();
    if (text.isEmpty()) {
      return UsageFields.empty();
    }

    UsageFields best = UsageFields.empty();
    for (JsonNode root : parsePayloads(text)) {
      UsageFields candidate = usageFromPayload(root);
      best = best.merge(candidate);
      if (candidate.hasAnyUsage() && isResponseCompleted(root)) {
        return best;
      }
    }
    return best;
  }

  private List<JsonNode> parsePayloads(String text) {
    List<JsonNode> payloads = new ArrayList<>();
    if (text.startsWith("{") || text.startsWith("[")) {
      readJson(text).ifPresent(payloads::add);
      return payloads;
    }

    for (String block : text.split("\\R\\R+")) {
      for (String line : block.split("\\R")) {
        String trimmed = line.trim();
        if (!trimmed.startsWith("data:")) {
          continue;
        }
        String payload = trimmed.substring(5).trim();
        if (!payload.isEmpty() && !"[DONE]".equals(payload)) {
          readJson(payload).ifPresent(payloads::add);
        }
      }
    }
    return payloads;
  }

  private java.util.Optional<JsonNode> readJson(String text) {
    try {
      return java.util.Optional.of(objectMapper.readTree(text));
    } catch (Exception ignored) {
      return java.util.Optional.empty();
    }
  }

  private UsageFields usageFromPayload(JsonNode root) {
    JsonNode response = objectAt(root, "response");
    JsonNode usage = firstObjectAt(response, "usage", root, "usage");
    String model = firstText(textAt(response, "model"), textAt(root, "model"));
    if (usage == null) {
      return new UsageFields(model, null, null, null, null);
    }

    Integer inputTokens =
        firstInteger(
            intAt(usage, "input_tokens"),
            intAt(usage, "prompt_tokens"),
            intAt(usage, "inputTokens"),
            intAt(usage, "promptTokens"));
    Integer outputTokens =
        firstInteger(
            intAt(usage, "output_tokens"),
            intAt(usage, "completion_tokens"),
            intAt(usage, "outputTokens"),
            intAt(usage, "completionTokens"));
    Integer cacheReadTokens =
        firstInteger(
            intAt(usage, "cache_read_input_tokens"),
            intAt(usage, "cache_read_tokens"),
            nestedIntAt(usage, "input_tokens_details", "cached_tokens"),
            nestedIntAt(usage, "prompt_tokens_details", "cached_tokens"));
    Integer cacheCreationTokens =
        firstInteger(
            intAt(usage, "cache_creation_input_tokens"),
            intAt(usage, "cache_creation_tokens"),
            nestedIntAt(usage, "input_tokens_details", "cache_creation_tokens"),
            nestedIntAt(usage, "prompt_tokens_details", "cache_creation_tokens"));

    return new UsageFields(model, inputTokens, outputTokens, cacheReadTokens, cacheCreationTokens);
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

  private boolean isResponseCompleted(JsonNode root) {
    return "response.completed".equals(textAt(root, "type"));
  }

  private JsonNode firstObjectAt(JsonNode firstParent, String firstName, JsonNode secondParent, String secondName) {
    JsonNode first = objectAt(firstParent, firstName);
    return first == null ? objectAt(secondParent, secondName) : first;
  }

  private JsonNode objectAt(JsonNode parent, String fieldName) {
    if (parent == null) {
      return null;
    }
    JsonNode value = parent.get(fieldName);
    return value == null || !value.isObject() ? null : value;
  }

  private String textAt(JsonNode parent, String fieldName) {
    if (parent == null) {
      return null;
    }
    JsonNode value = parent.get(fieldName);
    if (value == null || value.isNull()) {
      return null;
    }
    String text = value.asText();
    return text == null || text.isBlank() ? null : text;
  }

  private Integer nestedIntAt(JsonNode parent, String objectName, String fieldName) {
    return intAt(objectAt(parent, objectName), fieldName);
  }

  private Integer intAt(JsonNode parent, String fieldName) {
    if (parent == null) {
      return null;
    }
    JsonNode value = parent.get(fieldName);
    if (value == null || value.isNull()) {
      return null;
    }
    try {
      return Math.max(0, value.asInt());
    } catch (Exception ignored) {
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

  private Integer firstInteger(Integer... values) {
    for (Integer value : values) {
      if (value != null) {
        return value;
      }
    }
    return null;
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
        price.inputPrice().multiply(BigDecimal.valueOf(regularInputTokens(usage)))
            .add(price.outputPrice().multiply(BigDecimal.valueOf(usage.outputTokens())))
            .add(price.cachedInputPrice().multiply(BigDecimal.valueOf(usage.cacheReadTokens())))
            .add(price.cacheCreationPrice().multiply(BigDecimal.valueOf(usage.cacheCreationTokens())))
            .divide(MILLION, 6, RoundingMode.HALF_UP);
    return cost.multiply(billingSettingsRepository.costMultiplier()).setScale(6, RoundingMode.HALF_UP);
  }

  private int regularInputTokens(ParsedUsage usage) {
    return Math.max(0, usage.inputTokens() - usage.cacheReadTokens() - usage.cacheCreationTokens());
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

  private record UsageFields(
      String model,
      Integer inputTokens,
      Integer outputTokens,
      Integer cacheReadTokens,
      Integer cacheCreationTokens) {

    static UsageFields empty() {
      return new UsageFields(null, null, null, null, null);
    }

    boolean hasAnyUsage() {
      return inputTokens != null
          || outputTokens != null
          || cacheReadTokens != null
          || cacheCreationTokens != null;
    }

    UsageFields merge(UsageFields other) {
      return new UsageFields(
          firstText(other.model, model),
          firstInteger(other.inputTokens, inputTokens),
          firstInteger(other.outputTokens, outputTokens),
          firstInteger(other.cacheReadTokens, cacheReadTokens),
          firstInteger(other.cacheCreationTokens, cacheCreationTokens));
    }

    private static String firstText(String first, String second) {
      return first != null && !first.isBlank() ? first : second;
    }

    private static Integer firstInteger(Integer first, Integer second) {
      return first == null ? second : first;
    }
  }
}
