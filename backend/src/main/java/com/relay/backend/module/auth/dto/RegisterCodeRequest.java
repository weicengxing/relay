package com.relay.backend.module.auth.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public record RegisterCodeRequest(
    @NotBlank
        @Pattern(regexp = "^[1-9][0-9]{4,11}@qq\\.com$", message = "Only numeric QQ email is allowed")
        String email) {}

