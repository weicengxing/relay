package com.relay.backend.module.proxy;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.relay.backend.common.error.AppException;
import com.relay.backend.common.redis.RedisStateService;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

class UpstreamRouterTests {

  @Test
  void acquireSkipsExcludedAndBusyOpenAiProfiles() {
    RedisStateService redisStateService = mock(RedisStateService.class);
    UpstreamRouter router = router(redisStateService, services(1L, 2L, 3L));

    when(redisStateService.increment(eq("relay:upstream:cursor:codex"), any(Duration.class))).thenReturn(1L);
    when(redisStateService.increment(eq("relay:upstream:active:codex:2"), any(Duration.class))).thenReturn(21L);
    when(redisStateService.increment(eq("relay:upstream:active:codex:3"), any(Duration.class))).thenReturn(20L);

    UpstreamLease lease = router.acquire(ClientType.CODEX, Set.of(1L));

    assertThat(lease.config().id()).isEqualTo(3L);
    verify(redisStateService).decrement("relay:upstream:active:codex:2");

    lease.close();
    verify(redisStateService).decrement("relay:upstream:active:codex:3");
  }

  @Test
  void acquireSkipsExcludedAndBusyOpenAiTokenServices() {
    RedisStateService redisStateService = mock(RedisStateService.class);
    UpstreamRouter router = router(redisStateService, 1, tokenServices(1L, 2L, 3L));

    when(redisStateService.increment(eq("relay:upstream:cursor:codex"), any(Duration.class))).thenReturn(1L);
    when(redisStateService.increment(eq("relay:upstream:active:codex:2"), any(Duration.class))).thenReturn(21L);
    when(redisStateService.increment(eq("relay:upstream:active:codex:3"), any(Duration.class))).thenReturn(20L);

    UpstreamLease lease = router.acquire(ClientType.CODEX, Set.of(1L));

    assertThat(lease.config().id()).isEqualTo(3L);
    assertThat(lease.config().usesCodexProfileRequest()).isFalse();
    verify(redisStateService).decrement("relay:upstream:active:codex:2");

    lease.close();
    verify(redisStateService).decrement("relay:upstream:active:codex:3");
  }

  @Test
  void acquireFailsWhenEveryRemainingProfileIsBusy() {
    RedisStateService redisStateService = mock(RedisStateService.class);
    UpstreamRouter router = router(redisStateService, services(1L, 2L));

    when(redisStateService.increment(eq("relay:upstream:cursor:codex"), any(Duration.class))).thenReturn(1L);
    when(redisStateService.increment(eq("relay:upstream:active:codex:2"), any(Duration.class))).thenReturn(21L);

    assertThatThrownBy(() -> router.acquire(ClientType.CODEX, Set.of(1L)))
        .isInstanceOf(AppException.class)
        .hasMessage("All upstream services are busy");
    verify(redisStateService).decrement("relay:upstream:active:codex:2");
  }

  private UpstreamRouter router(RedisStateService redisStateService, List<OpenAiServiceConfig> services) {
    return router(redisStateService, 2, services);
  }

  private UpstreamRouter router(
      RedisStateService redisStateService, int openAiRequestMode, List<OpenAiServiceConfig> services) {
    OpenAiServiceRepository openAiServiceRepository = mock(OpenAiServiceRepository.class);
    ClaudeServiceRepository claudeServiceRepository = mock(ClaudeServiceRepository.class);
    ProxyRuntimeSettingsRepository settingsRepository = mock(ProxyRuntimeSettingsRepository.class);
    when(openAiServiceRepository.findAll()).thenReturn(services);
    when(settingsRepository.current()).thenReturn(new ProxyRuntimeSettings(openAiRequestMode, 20));
    return new UpstreamRouter(
        openAiServiceRepository, claudeServiceRepository, redisStateService, settingsRepository);
  }

  private List<OpenAiServiceConfig> services(Long... ids) {
    return java.util.Arrays.stream(ids).map(this::service).toList();
  }

  private OpenAiServiceConfig service(Long id) {
    Instant now = Instant.parse("2026-05-08T00:00:00Z");
    return new OpenAiServiceConfig(
        id,
        "https://chatgpt.com/backend-api/codex",
        "service-token-" + id,
        false,
        "",
        new CodexProfileConfig(
            id,
            id,
            "profile-" + id,
            "chatgpt",
            null,
            "access-token-" + id,
            null,
            null,
            null,
            null,
            null,
            "gpt-5.3-codex",
            "medium",
            null,
            now,
            now),
        now,
        now);
  }

  private List<OpenAiServiceConfig> tokenServices(Long... ids) {
    return java.util.Arrays.stream(ids).map(this::tokenService).toList();
  }

  private OpenAiServiceConfig tokenService(Long id) {
    Instant now = Instant.parse("2026-05-08T00:00:00Z");
    return new OpenAiServiceConfig(
        id,
        "https://api.openai.com/v1",
        "service-token-" + id,
        false,
        "",
        null,
        now,
        now);
  }
}
