package com.relay.backend.module.webchat.history;

import java.time.Instant;
import java.util.UUID;

public record ChatHistoryFile(
    Long id,
    UUID userId,
    int sequence,
    String objectKey,
    String contentUrl,
    long sizeBytes,
    int turnCount,
    Instant createdAt,
    Instant updatedAt) {}
