package com.relay.backend.module.apikey;

import java.time.Instant;
import java.util.UUID;

public record ApiKeyRecord(
    UUID userId, Long id, String keyHash, String keyValue, String name, String status, Instant createdAt) {}
