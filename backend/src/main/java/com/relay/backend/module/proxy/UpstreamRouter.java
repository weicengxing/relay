package com.relay.backend.module.proxy;

import com.relay.backend.common.error.AppException;
import com.relay.backend.common.error.ErrorCode;
import com.relay.backend.common.redis.RedisStateService;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Set;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

@Component
public class UpstreamRouter {
  private static final String CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann";
  private static final String CODEX_REFRESH_TOKEN_URL = "https://auth.openai.com/oauth/token";

  private final OpenAiServiceRepository openAiServiceRepository;
  private final ClaudeServiceRepository claudeServiceRepository;
  private final RedisStateService redisStateService;
  private final ProxyRuntimeSettingsRepository settingsRepository;
  private final ObjectMapper objectMapper = new ObjectMapper();
  private final HttpClient refreshClient =
      HttpClient.newBuilder()
          .connectTimeout(Duration.ofSeconds(30))
          .version(HttpClient.Version.HTTP_1_1)
          .build();

  public UpstreamRouter(
      OpenAiServiceRepository openAiServiceRepository,
      ClaudeServiceRepository claudeServiceRepository,
      RedisStateService redisStateService,
      ProxyRuntimeSettingsRepository settingsRepository) {
    this.openAiServiceRepository = openAiServiceRepository;
    this.claudeServiceRepository = claudeServiceRepository;
    this.redisStateService = redisStateService;
    this.settingsRepository = settingsRepository;
  }

  public UpstreamLease acquire(ClientType clientType) {
    return acquire(clientType, Set.of());
  }

  public UpstreamLease acquire(ClientType clientType, Set<Long> excludedServiceIds) {
    ProxyRuntimeSettings settings = settingsRepository.current();
    List<UpstreamConfig> configs =
        switch (clientType) {
          case CODEX -> openAiServiceRepository.findAll().stream()
              .filter(config -> settings.openAiRequestMode() == 2
                  ? config.codexProfile() != null
                  : config.codexProfile() == null)
              .map(
                  config ->
                      new UpstreamConfig(
                          config.id(),
                          config.apiEndpoint(),
                          config.token(),
                          settings.openAiRequestMode(),
                          settings.openAiConcurrentLimit(),
                          config.forceReplaceCodexModel(),
                          config.codexReplacementModel(),
                          config.codexProfile()))
              .toList();
          case CLAUDE -> claudeServiceRepository.findAll().stream()
              .map(
                  config ->
                      new UpstreamConfig(
                          config.id(),
                          config.apiEndpoint(),
                          config.token(),
                          1,
                          config.concurrentLimit(),
                          false,
                          "",
                          null))
              .toList();
          default -> throw new AppException(ErrorCode.VALIDATION_FAILED, "Unknown client type", HttpStatus.BAD_REQUEST);
        };

    if (configs.isEmpty()) {
      throw new AppException(ErrorCode.NOT_FOUND, "No upstream service configured", HttpStatus.NOT_FOUND);
    }

    List<UpstreamConfig> eligibleConfigs =
        configs.stream()
            .filter(config -> excludedServiceIds == null || !excludedServiceIds.contains(config.id()))
            .toList();
    if (eligibleConfigs.isEmpty()) {
      throw new AppException(ErrorCode.RATE_LIMITED, "No unused upstream service available", HttpStatus.TOO_MANY_REQUESTS);
    }

    long cursor = redisStateService.increment(cursorKey(clientType), Duration.ofDays(1));
    int start = Math.floorMod(cursor - 1, eligibleConfigs.size());
    for (int offset = 0; offset < eligibleConfigs.size(); offset++) {
      UpstreamConfig config = eligibleConfigs.get((start + offset) % eligibleConfigs.size());
      String activeKey = activeKey(clientType, config.id());
      long current = redisStateService.increment(activeKey, Duration.ofHours(2));
      if (current <= config.concurrentLimit()) {
        return new UpstreamLease(config, () -> redisStateService.decrement(activeKey));
      }
      redisStateService.decrement(activeKey);
    }

    throw new AppException(ErrorCode.RATE_LIMITED, "All upstream services are busy", HttpStatus.TOO_MANY_REQUESTS);
  }

  public UpstreamConfig refreshCodexProfile(UpstreamConfig config) {
    if (config == null || !config.usesCodexProfileRequest() || config.codexProfile() == null) {
      return null;
    }
    CodexProfileConfig profile = config.codexProfile();
    if (profile.refreshToken() == null || profile.refreshToken().isBlank()) {
      return null;
    }

    try {
      ObjectNode payload = objectMapper.createObjectNode();
      payload.put("client_id", firstNonBlank(profile.clientId(), CODEX_CLIENT_ID));
      payload.put("grant_type", "refresh_token");
      payload.put("refresh_token", profile.refreshToken().trim());
      HttpRequest request =
          HttpRequest.newBuilder(URI.create(CODEX_REFRESH_TOKEN_URL))
              .timeout(Duration.ofSeconds(60))
              .header("accept", "application/json")
              .header("content-type", "application/json")
              .header("originator", "codex_cli_rs")
              .header("user-agent", "codex_cli_rs/0.126.0 (Windows 10; x86_64)")
              .header("version", "0.126.0")
              .POST(HttpRequest.BodyPublishers.ofByteArray(objectMapper.writeValueAsBytes(payload)))
              .build();
      HttpResponse<String> response = refreshClient.send(request, HttpResponse.BodyHandlers.ofString());
      if (response.statusCode() < 200 || response.statusCode() >= 300) {
        return null;
      }
      JsonNode body = objectMapper.readTree(response.body());
      String accessToken = textOrNull(body.get("access_token"));
      if (accessToken == null || accessToken.isBlank()) {
        return null;
      }
      String idToken = firstNonBlank(textOrNull(body.get("id_token")), profile.idToken());
      String refreshToken = firstNonBlank(textOrNull(body.get("refresh_token")), profile.refreshToken());
      openAiServiceRepository.updateCodexProfileTokens(
          profile.openAiServiceId(), accessToken, idToken, refreshToken);
      CodexProfileConfig refreshedProfile =
          new CodexProfileConfig(
              profile.id(),
              profile.openAiServiceId(),
              profile.profileName(),
              profile.authMode(),
              profile.openAiApiKey(),
              accessToken,
              profile.accountId(),
              idToken,
              refreshToken,
              profile.clientId(),
              profile.baseUrl(),
              profile.model(),
              profile.reasoningEffort(),
              Instant.now(),
              profile.createdAt(),
              Instant.now());
      return new UpstreamConfig(
          config.id(),
          config.apiEndpoint(),
          accessToken,
          config.requestMode(),
          config.concurrentLimit(),
          config.forceReplaceCodexModel(),
          config.codexReplacementModel(),
          refreshedProfile);
    } catch (Exception exception) {
      return null;
    }
  }

  private String textOrNull(JsonNode node) {
    if (node == null || node.isNull()) {
      return null;
    }
    String text = node.asText();
    return text == null || text.isBlank() ? null : text;
  }

  private String firstNonBlank(String... values) {
    for (String value : values) {
      if (value != null && !value.isBlank()) {
        return value;
      }
    }
    return null;
  }

  private String cursorKey(ClientType clientType) {
    return "relay:upstream:cursor:" + clientType.name().toLowerCase();
  }

  private String activeKey(ClientType clientType, Long serviceId) {
    return "relay:upstream:active:" + clientType.name().toLowerCase() + ":" + serviceId;
  }
}
