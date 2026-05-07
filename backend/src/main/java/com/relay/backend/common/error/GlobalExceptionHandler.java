package com.relay.backend.common.error;

import com.relay.backend.common.api.ApiError;
import com.relay.backend.common.api.ApiResponse;
import jakarta.validation.ConstraintViolationException;
import java.util.Map;
import java.util.stream.Collectors;
import org.springframework.context.support.DefaultMessageSourceResolvable;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {

  @ExceptionHandler(AppException.class)
  public ResponseEntity<ApiResponse<Void>> handleAppException(AppException exception) {
    return ResponseEntity.status(exception.status())
        .body(ApiResponse.fail(ApiError.of(exception.code(), exception.getMessage())));
  }

  @ExceptionHandler(MethodArgumentNotValidException.class)
  public ResponseEntity<ApiResponse<Void>> handleMethodArgumentNotValid(
      MethodArgumentNotValidException exception) {
    Map<String, String> details =
        exception.getBindingResult().getFieldErrors().stream()
            .collect(
                Collectors.toMap(
                    fieldError -> fieldError.getField(),
                    DefaultMessageSourceResolvable::getDefaultMessage,
                    (first, ignored) -> first));

    return ResponseEntity.status(HttpStatus.BAD_REQUEST)
        .body(
            ApiResponse.fail(
                ApiError.of(ErrorCode.VALIDATION_FAILED, "Request validation failed", details)));
  }

  @ExceptionHandler(ConstraintViolationException.class)
  public ResponseEntity<ApiResponse<Void>> handleConstraintViolation(
      ConstraintViolationException exception) {
    Map<String, String> details =
        exception.getConstraintViolations().stream()
            .collect(
                Collectors.toMap(
                    violation -> violation.getPropertyPath().toString(),
                    violation -> violation.getMessage(),
                    (first, ignored) -> first));

    return ResponseEntity.status(HttpStatus.BAD_REQUEST)
        .body(
            ApiResponse.fail(
                ApiError.of(ErrorCode.VALIDATION_FAILED, "Request validation failed", details)));
  }

  @ExceptionHandler(Exception.class)
  public ResponseEntity<ApiResponse<Void>> handleUnhandled(Exception exception) {
    return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
        .body(
            ApiResponse.fail(
                ApiError.of(ErrorCode.INTERNAL_ERROR, "Unexpected server error")));
  }
}

