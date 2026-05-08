package com.relay.backend.module.apikey.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateApiKeyRequest(@NotBlank @Size(max = 60) String name) {}
