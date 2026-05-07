package com.relay.backend.api;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class HealthControllerTests {

  private final HealthController controller = new HealthController();

  @Test
  void healthReturnsWrappedStatus() {
    var response = controller.health();

    assertThat(response.success()).isTrue();
    assertThat(response.error()).isNull();
    assertThat(response.data().status()).isEqualTo("UP");
    assertThat(response.data().service()).isEqualTo("relay-backend");
  }

  @Test
  void bootstrapReturnsStableModuleList() {
    var response = controller.bootstrap();

    assertThat(response.success()).isTrue();
    assertThat(response.data().status()).isEqualTo("ready");
    assertThat(response.data().modules())
        .containsExactlyInAnyOrder("auth", "user", "billing", "proxy", "admin", "log");
  }
}
