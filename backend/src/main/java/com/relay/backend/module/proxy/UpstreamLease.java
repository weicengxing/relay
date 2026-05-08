package com.relay.backend.module.proxy;

public record UpstreamLease(UpstreamConfig config, Runnable release) implements AutoCloseable {

  @Override
  public void close() {
    release.run();
  }
}
