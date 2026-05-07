package com.relay.backend.module.auth.dto;

import java.math.BigDecimal;
import java.util.UUID;

public record AuthResponse(UUID userId, String email, BigDecimal balance, String token) {}

