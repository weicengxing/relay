package com.relay.backend.module.auth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.relay.backend.common.error.AppException;
import com.relay.backend.common.error.ErrorCode;
import com.relay.backend.module.auth.dto.LoginRequest;
import com.relay.backend.module.auth.dto.RegisterRequest;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@ActiveProfiles("test")
@Transactional
class AuthServiceTests {

  @Autowired private AuthService authService;
  @Autowired private JdbcTemplate jdbcTemplate;

  @Test
  void registersAndLogsInNumericQqUser() {
    var registered =
        authService.register(new RegisterRequest("123456789@qq.com", "password123"), "10.0.0.1");
    var loggedIn = authService.login(new LoginRequest("123456789@qq.com", "password123"));

    assertThat(registered.email()).isEqualTo("123456789@qq.com");
    assertThat(loggedIn.userId()).isEqualTo(registered.userId());
    assertThat(loggedIn.token()).isNotBlank();
  }

  @Test
  void rejectsSecondRegistrationFromSameIp() {
    authService.register(new RegisterRequest("123456789@qq.com", "password123"), "10.0.0.1");

    assertThatThrownBy(
            () ->
                authService.register(
                    new RegisterRequest("987654321@qq.com", "password123"), "10.0.0.1"))
        .isInstanceOf(AppException.class)
        .extracting("code")
        .isEqualTo(ErrorCode.CONFLICT);
  }

  @Test
  void schemaContainsOpenAiServicesTable() {
    Integer count =
        jdbcTemplate.queryForObject(
            "select count(*) from information_schema.tables where table_name = 'openai_services'",
            Integer.class);

    assertThat(count).isEqualTo(1);
  }
}

