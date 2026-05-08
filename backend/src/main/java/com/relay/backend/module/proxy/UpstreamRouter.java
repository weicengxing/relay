package com.relay.backend.module.proxy;

import com.relay.backend.common.error.AppException;
import com.relay.backend.common.error.ErrorCode;
import com.relay.backend.common.redis.RedisStateService;
import java.time.Duration;
import java.util.List;
import java.util.Set;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

@Component
public class UpstreamRouter {

  private final OpenAiServiceRepository openAiServiceRepository;
  private final ClaudeServiceRepository claudeServiceRepository;
  private final RedisStateService redisStateService;
  private final ProxyRuntimeSettingsRepository settingsRepository;

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

  private String cursorKey(ClientType clientType) {
    return "relay:upstream:cursor:" + clientType.name().toLowerCase();
  }

  private String activeKey(ClientType clientType, Long serviceId) {
    return "relay:upstream:active:" + clientType.name().toLowerCase() + ":" + serviceId;
  }
}
