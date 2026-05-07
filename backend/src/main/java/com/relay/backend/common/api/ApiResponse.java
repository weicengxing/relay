package com.relay.backend.common.api;

import java.time.Instant;

public record ApiResponse<T>(boolean success, T data, ApiError error, Instant timestamp) {

  public static <T> ApiResponse<T> ok(T data) {
    return new ApiResponse<>(true, data, null, Instant.now());
  }

  public static ApiResponse<Void> ok() {
    return new ApiResponse<>(true, null, null, Instant.now());
  }

  public static ApiResponse<Void> fail(ApiError error) {
    return new ApiResponse<>(false, null, error, Instant.now());
  }
}

