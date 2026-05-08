package com.relay.backend.module.proxy;

import java.time.Instant;

public record OpenAiServiceConfig(
    Long id,
    String apiEndpoint,
    String token,
    CodexProfileConfig codexProfile,
    Instant createdAt,
    Instant updatedAt) {}
