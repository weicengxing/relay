package com.relay.backend.module.log.dto;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record RequestLogResponse(
    Long id,
    Instant createdAt,
    String token,
    String group,
    String type,
    String model,
    int useTimeMs,
    int firstTokenMs,
    int inputTokens,
    int outputTokens,
    int cacheReadTokens,
    int cacheCreationTokens,
    BigDecimal cost,
    String ip,
    String status,
    Long upstreamServiceId,
    List<String> detailLines) {}
