package com.relay.backend.common.api;

import java.util.Map;

public record ApiError(String code, String message, Map<String, String> details) {

  public static ApiError of(String code, String message) {
    return new ApiError(code, message, Map.of());
  }

  public static ApiError of(String code, String message, Map<String, String> details) {
    return new ApiError(code, message, details == null ? Map.of() : Map.copyOf(details));
  }
}

