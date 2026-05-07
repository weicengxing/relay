package com.relay.backend.common.error;

public final class ErrorCode {

  public static final String VALIDATION_FAILED = "VALIDATION_FAILED";
  public static final String UNAUTHORIZED = "UNAUTHORIZED";
  public static final String FORBIDDEN = "FORBIDDEN";
  public static final String NOT_FOUND = "NOT_FOUND";
  public static final String CONFLICT = "CONFLICT";
  public static final String RATE_LIMITED = "RATE_LIMITED";
  public static final String INVALID_CREDENTIALS = "INVALID_CREDENTIALS";
  public static final String INTERNAL_ERROR = "INTERNAL_ERROR";

  private ErrorCode() {}
}
