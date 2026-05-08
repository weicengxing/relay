package com.relay.backend.module.apikey;

import static org.assertj.core.api.Assertions.assertThat;

import com.relay.backend.module.apikey.dto.CreateApiKeyRequest;
import com.relay.backend.module.auth.AuthService;
import com.relay.backend.module.auth.EmailVerificationService;
import com.relay.backend.module.auth.dto.RegisterRequest;
import com.relay.backend.test.RedisTestConfig;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@ActiveProfiles("test")
@Transactional
@org.springframework.context.annotation.Import(RedisTestConfig.class)
class ApiKeyServiceTests {

  @Autowired private ApiKeyService apiKeyService;
  @Autowired private AuthService authService;
  @Autowired private EmailVerificationService emailVerificationService;

  @Test
  void createsListsAndRevokesApiKey() {
    emailVerificationService.putRegisterCodeForTest("123456789@qq.com", "123456");
    var user =
        authService.register(
            new RegisterRequest("123456789@qq.com", "password123", "123456"), "10.0.0.1");

    var created = apiKeyService.create(user.userId(), new CreateApiKeyRequest("Local dev"));
    var listed = apiKeyService.list(user.userId());
    apiKeyService.revoke(user.userId(), created.id());

    assertThat(created.key()).startsWith("relay_");
    assertThat(listed).hasSize(1);
    assertThat(listed.getFirst().name()).isEqualTo("Local dev");
    assertThat(apiKeyService.list(user.userId())).isEmpty();
  }
}
