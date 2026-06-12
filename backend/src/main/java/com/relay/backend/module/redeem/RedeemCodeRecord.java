package com.relay.backend.module.redeem;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record RedeemCodeRecord(
    Long id,
    String code,
    String batch,
    BigDecimal amount,
    Instant expiresAt,
    UUID holderUserId,
    String redeemedIp,
    Instant redeemedAt,
    Instant expiredDeductedAt,
    Instant createdAt,
    Instant updatedAt) {}
