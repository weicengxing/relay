package com.relay.backend.module.redeem.dto;

import jakarta.validation.constraints.NotBlank;

public record RedeemCodeRequest(@NotBlank String code) {}
