package com.relay.backend.module.proxy;

import java.time.Instant;

public record OpenAiServiceConfig(
    Long id,
    String apiEndpoint,
    String token,
    int requestMode,
    int concurrentLimit,
    CodexProfileConfig codexProfile,
    Instant createdAt,
    Instant updatedAt) {}
