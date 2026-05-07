package com.relay.backend.module.auth;

import static org.assertj.core.api.Assertions.assertThat;

import com.relay.backend.config.AppProperties;
import com.relay.backend.module.user.UserAccount;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class AuthTokenServiceTests {

  @Test
  void issuesSignedJwtShapeToken() {
    AppProperties properties = new AppProperties();
    properties.getSecurity().setJwtSecret("test-secret");
    AuthTokenService tokenService = new AuthTokenService(properties);
    UserAccount user =
        new UserAccount(
            UUID.randomUUID(),
            "123456789@qq.com",
            "hash",
            "127.0.0.1",
            BigDecimal.ZERO,
            "active",
            Instant.now());

    String token = tokenService.issue(user);

    assertThat(token.split("\\.")).hasSize(3);
  }
}
