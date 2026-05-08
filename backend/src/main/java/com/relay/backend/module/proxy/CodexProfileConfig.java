package com.relay.backend.module.proxy;

import java.time.Instant;

public record CodexProfileConfig(
    Long id,
    Long openAiServiceId,
    String profileName,
    String authMode,
    String openAiApiKey,
    String accessToken,
    String accountId,
    String idToken,
    String refreshToken,
    String clientId,
    String baseUrl,
    String model,
    String reasoningEffort,
    Instant lastRefresh,
    Instant createdAt,
    Instant updatedAt) {}
