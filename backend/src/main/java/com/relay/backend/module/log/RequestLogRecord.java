package com.relay.backend.module.log;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record RequestLogRecord(
    Long id,
    UUID userId,
    Long apiKeyId,
    String tokenName,
    String groupKey,
    String requestType,
    String clientType,
    String model,
    int useTimeMs,
    int firstTokenMs,
    int promptTokens,
    int completionTokens,
    int cacheReadTokens,
    int cacheCreationTokens,
    BigDecimal cost,
    String ip,
    String status,
    Long upstreamServiceId,
    String detail,
    Instant createdAt) {}
