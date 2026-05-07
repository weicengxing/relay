package com.relay.backend.module.auth;

import static org.assertj.core.api.Assertions.assertThat;

import com.relay.backend.module.auth.dto.RegisterRequest;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;

class RegisterRequestTests {

  private final Validator validator = Validation.buildDefaultValidatorFactory().getValidator();

  @Test
  void acceptsNumericQqEmail() {
    var violations = validator.validate(new RegisterRequest("123456789@qq.com", "password123"));

    assertThat(violations).isEmpty();
  }

  @Test
  void rejectsNonNumericQqEmail() {
    var violations = validator.validate(new RegisterRequest("relay@qq.com", "password123"));

    assertThat(violations).isNotEmpty();
  }

  @Test
  void rejectsNonQqEmail() {
    var violations = validator.validate(new RegisterRequest("123456789@example.com", "password123"));

    assertThat(violations).isNotEmpty();
  }
}

