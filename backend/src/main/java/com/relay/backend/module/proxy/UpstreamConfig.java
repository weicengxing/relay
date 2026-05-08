package com.relay.backend.module.proxy;

public record UpstreamConfig(
    Long id,
    String apiEndpoint,
    String token,
    int requestMode,
    int concurrentLimit,
    CodexProfileConfig codexProfile) {

  public boolean usesCodexProfileRequest() {
    return requestMode == 2;
  }
}
