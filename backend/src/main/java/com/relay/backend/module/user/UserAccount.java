package com.relay.backend.module.user;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record UserAccount(
    UUID id,
    String email,
    String passwordHash,
    String registrationIp,
    BigDecimal balance,
    String status,
    Instant createdAt) {}

