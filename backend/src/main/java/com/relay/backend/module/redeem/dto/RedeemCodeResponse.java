package com.relay.backend.module.redeem.dto;

import java.math.BigDecimal;
import java.time.Instant;

public record RedeemCodeResponse(BigDecimal amount, BigDecimal balance, Instant expiresAt) {}
