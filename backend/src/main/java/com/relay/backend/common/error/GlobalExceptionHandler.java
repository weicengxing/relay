package com.relay.backend.common.error;

import com.relay.backend.common.api.ApiError;
import com.relay.backend.common.api.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.ConstraintViolationException;
import java.util.Map;
import java.util.stream.Collectors;
import org.springframework.context.support.DefaultMessageSourceResolvable;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {

  private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

  @ExceptionHandler(AppException.class)
  public ResponseEntity<?> handleAppException(
      AppException exception, HttpServletRequest request, HttpServletResponse response) {
    if (shouldReturnEventStream(request, response)) {
      return eventStreamError(exception.status(), exception.getMessage());
    }
    return ResponseEntity.status(exception.status())
        .body(ApiResponse.fail(ApiError.of(exception.code(), exception.getMessage())));
  }

  @ExceptionHandler(MethodArgumentNotValidException.class)
  public ResponseEntity<?> handleMethodArgumentNotValid(
      MethodArgumentNotValidException exception,
      HttpServletRequest request,
      HttpServletResponse response) {
    Map<String, String> details =
        exception.getBindingResult().getFieldErrors().stream()
            .collect(
                Collectors.toMap(
                    fieldError -> fieldError.getField(),
                    DefaultMessageSourceResolvable::getDefaultMessage,
                    (first, ignored) -> first));

    if (shouldReturnEventStream(request, response)) {
      return eventStreamError(HttpStatus.BAD_REQUEST, "Request validation failed");
    }
    return ResponseEntity.status(HttpStatus.BAD_REQUEST)
        .body(
            ApiResponse.fail(
                ApiError.of(ErrorCode.VALIDATION_FAILED, "Request validation failed", details)));
  }

  @ExceptionHandler(ConstraintViolationException.class)
  public ResponseEntity<?> handleConstraintViolation(
      ConstraintViolationException exception,
      HttpServletRequest request,
      HttpServletResponse response) {
    Map<String, String> details =
        exception.getConstraintViolations().stream()
            .collect(
                Collectors.toMap(
                    violation -> violation.getPropertyPath().toString(),
                    violation -> violation.getMessage(),
                    (first, ignored) -> first));

    if (shouldReturnEventStream(request, response)) {
      return eventStreamError(HttpStatus.BAD_REQUEST, "Request validation failed");
    }
    return ResponseEntity.status(HttpStatus.BAD_REQUEST)
        .body(
            ApiResponse.fail(
                ApiError.of(ErrorCode.VALIDATION_FAILED, "Request validation failed", details)));
  }

  @ExceptionHandler(Exception.class)
  public ResponseEntity<?> handleUnhandled(
      Exception exception, HttpServletRequest request, HttpServletResponse response) {
    log.error("Unhandled request error: {} {}", request.getMethod(), request.getRequestURI(), exception);
    if (shouldReturnEventStream(request, response)) {
      return eventStreamError(HttpStatus.INTERNAL_SERVER_ERROR, "Unexpected server error");
    }
    return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
        .body(
            ApiResponse.fail(
                ApiError.of(ErrorCode.INTERNAL_ERROR, "Unexpected server error")));
  }

  private boolean shouldReturnEventStream(HttpServletRequest request, HttpServletResponse response) {
    String responseContentType = response.getContentType();
    if (containsEventStream(responseContentType)) {
      return true;
    }
    String path = request.getRequestURI();
    String accept = request.getHeader(HttpHeaders.ACCEPT);
    return (path.startsWith("/v1/") || path.startsWith("/backend-api/codex/"))
        && containsEventStream(accept);
  }

  private boolean containsEventStream(String value) {
    return value != null && value.toLowerCase().contains(MediaType.TEXT_EVENT_STREAM_VALUE);
  }

  private ResponseEntity<String> eventStreamError(HttpStatus status, String message) {
    String body =
        "{\"error\":{\"message\":\""
            + jsonEscape(message)
            + "\",\"type\":\"relay_error\",\"code\":\"relay_error\"}}";
    return ResponseEntity.status(status)
        .contentType(MediaType.TEXT_EVENT_STREAM)
        .body("event: error\ndata: " + body + "\n\n");
  }

  private String jsonEscape(String value) {
    if (value == null) {
      return "";
    }
    return value.replace("\\", "\\\\").replace("\"", "\\\"");
  }
}

