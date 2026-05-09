package com.relay.backend.module.webchat;

import java.time.Instant;

public record WebChatModelConfig(
    Long id,
    String name,
    String baseUrl,
    String model,
    String authHeader,
    String bearerToken,
    String accountId,
    String conduitToken,
    String sentinelToken,
    String cookie,
    String oaiDeviceId,
    String oaiSessionId,
    String oaiClientBuildNumber,
    String oaiClientVersion,
    String oaiIs,
    String userAgent,
    boolean callPrepare,
    boolean enabled,
    Instant createdAt,
    Instant updatedAt) {}
