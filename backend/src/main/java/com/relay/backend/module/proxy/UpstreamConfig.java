package com.relay.backend.module.proxy;

public record UpstreamConfig(Long id, String apiEndpoint, String token, int concurrentLimit) {}
