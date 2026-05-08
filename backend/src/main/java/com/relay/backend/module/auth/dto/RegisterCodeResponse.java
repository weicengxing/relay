package com.relay.backend.module.auth.dto;

public record RegisterCodeResponse(String email, int expiresInMinutes) {}

