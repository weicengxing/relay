package com.relay.backend.module.proxy;

import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.Set;

final class UpstreamQuotaErrorDetector {

  private static final Set<Integer> RETRYABLE_STATUS_CODES = Set.of(401, 402, 403, 429);
  private static final Set<String> QUOTA_ERROR_MARKERS =
      Set.of(
          "insufficient_quota",
          "rate_limit_exceeded",
          "quota",
          "billing",
          "credit",
          "balance",
          "rate limit",
          "额度",
          "配额",
          "余额");

  private UpstreamQuotaErrorDetector() {}

  static boolean isRetryableStatus(int statusCode) {
    return RETRYABLE_STATUS_CODES.contains(statusCode);
  }

  static boolean isRetryableQuotaError(int statusCode, byte[] body) {
    if (!isRetryableStatus(statusCode)) {
      return false;
    }
    if (body == null || body.length == 0) {
      return statusCode == 402;
    }

    String text = new String(body, StandardCharsets.UTF_8).toLowerCase(Locale.ROOT);
    for (String marker : QUOTA_ERROR_MARKERS) {
      if (text.contains(marker)) {
        return true;
      }
    }
    return false;
  }
}
