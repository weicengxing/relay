package com.relay.backend.module.auth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.relay.backend.common.error.AppException;
import com.relay.backend.common.error.ErrorCode;
import com.relay.backend.module.auth.dto.LoginRequest;
import com.relay.backend.module.auth.dto.RegisterRequest;
import com.relay.backend.test.RedisTestConfig;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@ActiveProfiles("test")
@Transactional
@org.springframework.context.annotation.Import(RedisTestConfig.class)
class AuthServiceTests {

  @Autowired private AuthService authService;
  @Autowired private EmailVerificationService emailVerificationService;
  @Autowired private JdbcTemplate jdbcTemplate;

  @Test
  void registersAndLogsInNumericQqUser() {
    emailVerificationService.putRegisterCodeForTest("123456789@qq.com", "123456");
    var registered =
        authService.register(
            new RegisterRequest("123456789@qq.com", "password123", "123456"), "10.0.0.1");
    var loggedIn = authService.login(new LoginRequest("123456789@qq.com", "password123"));

    assertThat(registered.email()).isEqualTo("123456789@qq.com");
    assertThat(registered.balance()).isEqualByComparingTo("5.000000");
    assertThat(loggedIn.userId()).isEqualTo(registered.userId());
    assertThat(loggedIn.balance()).isEqualByComparingTo("5.000000");
    assertThat(loggedIn.token()).isNotBlank();
  }

  @Test
  void rejectsSecondRegistrationFromSameIp() {
    emailVerificationService.putRegisterCodeForTest("123456789@qq.com", "123456");
    authService.register(new RegisterRequest("123456789@qq.com", "password123", "123456"), "10.0.0.1");
    emailVerificationService.putRegisterCodeForTest("987654321@qq.com", "123456");

    assertThatThrownBy(
            () ->
                authService.register(
                    new RegisterRequest("987654321@qq.com", "password123", "123456"), "10.0.0.1"))
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

  @Test
  void schemaContainsCodexProfileModeTables() {
    Integer codexProfileTables =
        jdbcTemplate.queryForObject(
            "select count(*) from information_schema.tables where table_name = 'openai_codex_profiles'",
            Integer.class);
    Integer appSettingsTables =
        jdbcTemplate.queryForObject(
            "select count(*) from information_schema.tables where table_name = 'app_settings'",
            Integer.class);
    Integer defaultSettings =
        jdbcTemplate.queryForObject(
            """
            select count(*)
            from app_settings
            where setting_key in ('openai.request_mode', 'openai.concurrent_limit', 'announcements.badge_default')
            """,
            Integer.class);

    assertThat(codexProfileTables).isEqualTo(1);
    assertThat(appSettingsTables).isEqualTo(1);
    assertThat(defaultSettings).isEqualTo(3);
  }
}
