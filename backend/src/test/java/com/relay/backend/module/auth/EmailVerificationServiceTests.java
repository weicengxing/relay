package com.relay.backend.module.auth;

import static org.assertj.core.api.Assertions.assertThat;

import com.relay.backend.config.AppProperties;
import com.relay.backend.common.redis.RedisStateService;
import com.relay.backend.module.auth.dto.RegisterCodeResponse;
import com.relay.backend.test.RedisTestConfig;
import org.junit.jupiter.api.Test;

class EmailVerificationServiceTests {

  private static class StubMailSender implements VerificationMailSender {
    private String email;
    private String code;

    @Override
    public void sendRegisterCode(String email, String code, int ttlMinutes) {
      this.email = email;
      this.code = code;
    }
  }

  @Test
  void storesAndSendsVerificationCode() {
    AppProperties properties = new AppProperties();
    StubMailSender mailSender = new StubMailSender();
    RedisStateService redisStateService =
        new RedisStateService(new RedisTestConfig().stringRedisTemplate());
    EmailVerificationService service =
        new EmailVerificationService(properties, mailSender, redisStateService);

    RegisterCodeResponse response = service.sendRegisterCode("123456789@qq.com");

    assertThat(response.email()).isEqualTo("123456789@qq.com");
    assertThat(mailSender.email).isEqualTo("123456789@qq.com");
    assertThat(mailSender.code).hasSize(6);
  }
}
