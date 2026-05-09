package com.relay.backend.module.proxy;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

import com.relay.backend.common.web.ClientIpResolver;
import com.relay.backend.module.apikey.ApiKeyService;
import com.relay.backend.module.log.RequestLogService;
import com.relay.backend.module.user.UserRepository;
import java.lang.reflect.Method;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class ProxyControllerTests {

  @Test
  void normalizesClaudeXiaomiModelToLowercase() throws Exception {
    ProxyController controller =
        new ProxyController(
            mock(ApiKeyService.class),
            mock(ClientTypeDetector.class),
            mock(CodexRequestCaptureService.class),
            mock(UpstreamRouter.class),
            mock(RequestLogService.class),
            mock(UserRepository.class),
            mock(ClientIpResolver.class),
            new ObjectMapper());

    Method method =
        ProxyController.class.getDeclaredMethod(
            "normalizeUpstreamBody", byte[].class, UpstreamConfig.class, ClientType.class, boolean.class);
    method.setAccessible(true);

    byte[] normalized =
        (byte[])
            method.invoke(
                controller,
                """
                {"model":"MiMo-V2.5-Pro","max_tokens":16,"messages":[{"role":"user","content":"hi"}]}
                """
                    .getBytes(java.nio.charset.StandardCharsets.UTF_8),
                new UpstreamConfig(
                    1L,
                    "https://token-plan-cn.xiaomimimo.com/anthropic",
                    "token",
                    1,
                    20,
                    null),
                ClientType.CLAUDE,
                false);

    assertThat(new String(normalized, java.nio.charset.StandardCharsets.UTF_8))
        .contains("\"model\":\"mimo-v2.5-pro\"");
  }
}
