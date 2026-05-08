package com.relay.backend.module.apikey.dto;

import java.time.Instant;

public record ApiKeyResponse(Long id, String name, String key, String status, Instant createdAt) {}
