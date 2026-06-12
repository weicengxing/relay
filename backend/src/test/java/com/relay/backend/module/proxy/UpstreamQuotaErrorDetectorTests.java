package com.relay.backend.module.proxy;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class UpstreamQuotaErrorDetectorTests {

  @Test
  void detectsInsufficientQuotaError() {
    byte[] body =
        """
        {"error":{"message":"You exceeded your current quota.","code":"insufficient_quota"}}
        """
            .getBytes(StandardCharsets.UTF_8);

    assertThat(UpstreamQuotaErrorDetector.isRetryableQuotaError(429, body)).isTrue();
  }

  @Test
  void detectsBillingAndBalanceErrors() {
    assertThat(UpstreamQuotaErrorDetector.isRetryableQuotaError(402, "billing hard limit reached".getBytes()))
        .isTrue();
    assertThat(UpstreamQuotaErrorDetector.isRetryableQuotaError(403, "余额不足".getBytes(StandardCharsets.UTF_8)))
        .isTrue();
  }

  @Test
  void ignoresAuthenticationAndGenericErrors() {
    assertThat(UpstreamQuotaErrorDetector.isRetryableQuotaError(401, "insufficient_quota".getBytes()))
        .isTrue();
    assertThat(UpstreamQuotaErrorDetector.isRetryableQuotaError(429, "temporary upstream overload".getBytes()))
        .isFalse();
  }

  @Test
  void inspectsRetryableQuotaStatusesForAnyCodexRequestMode() {
    assertThat(ProxyController.shouldInspectQuotaRetry(ClientType.CODEX, 429)).isTrue();
    assertThat(ProxyController.shouldInspectQuotaRetry(ClientType.CODEX, 401)).isTrue();
    assertThat(ProxyController.shouldInspectQuotaRetry(ClientType.CODEX, 402)).isTrue();
    assertThat(ProxyController.shouldInspectQuotaRetry(ClientType.CLAUDE, 429)).isFalse();
    assertThat(ProxyController.shouldInspectQuotaRetry(ClientType.CODEX, 500)).isFalse();
  }
}
