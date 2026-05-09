package com.relay.backend.module.webchat.history.dto;

import java.time.Instant;

public record ChatHistoryFileResponse(
    Long id,
    int sequence,
    String objectKey,
    String contentUrl,
    long sizeBytes,
    int turnCount,
    Instant createdAt,
    Instant updatedAt) {}
