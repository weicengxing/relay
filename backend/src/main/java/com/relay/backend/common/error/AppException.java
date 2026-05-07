package com.relay.backend.common.error;

import org.springframework.http.HttpStatus;

public class AppException extends RuntimeException {

  private final String code;
  private final HttpStatus status;

  public AppException(String code, String message, HttpStatus status) {
    super(message);
    this.code = code;
    this.status = status;
  }

  public String code() {
    return code;
  }

  public HttpStatus status() {
    return status;
  }
}

