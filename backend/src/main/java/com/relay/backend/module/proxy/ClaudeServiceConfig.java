package com.relay.backend.module.proxy;

import java.time.Instant;

public record ClaudeServiceConfig(
    Long id, String apiEndpoint, String token, int concurrentLimit, Instant createdAt, Instant updatedAt) {}
