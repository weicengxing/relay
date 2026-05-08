package com.relay.backend.module.log;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

public final class UpstreamResponseDetailCodec {

  public static final String GZIP_BASE64_PREFIX = "gzip+base64:";
  private static final int COMPRESS_THRESHOLD_BYTES = 64 * 1024;

  private UpstreamResponseDetailCodec() {}

  public static String encode(byte[] body) {
    if (body == null || body.length == 0) {
      return "";
    }
    if (body.length <= COMPRESS_THRESHOLD_BYTES) {
      return new String(body, StandardCharsets.UTF_8);
    }
    return GZIP_BASE64_PREFIX + Base64.getEncoder().encodeToString(gzip(body));
  }

  public static String decode(String detail) {
    if (detail == null || detail.isBlank()) {
      return null;
    }
    if (!detail.startsWith(GZIP_BASE64_PREFIX)) {
      return detail;
    }
    byte[] compressed = Base64.getDecoder().decode(detail.substring(GZIP_BASE64_PREFIX.length()));
    return new String(gunzip(compressed), StandardCharsets.UTF_8);
  }

  private static byte[] gzip(byte[] body) {
    try {
      ByteArrayOutputStream outputStream = new ByteArrayOutputStream();
      try (GZIPOutputStream gzipStream = new GZIPOutputStream(outputStream)) {
        gzipStream.write(body);
      }
      return outputStream.toByteArray();
    } catch (IOException exception) {
      throw new IllegalStateException("Unable to compress upstream response detail", exception);
    }
  }

  private static byte[] gunzip(byte[] body) {
    try (GZIPInputStream gzipStream = new GZIPInputStream(new ByteArrayInputStream(body))) {
      return gzipStream.readAllBytes();
    } catch (IOException exception) {
      throw new IllegalArgumentException("Unable to decode upstream response detail", exception);
    }
  }
}
