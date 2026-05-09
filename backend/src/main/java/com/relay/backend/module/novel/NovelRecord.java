package com.relay.backend.module.novel;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record NovelRecord(
    Long id,
    UUID userId,
    String title,
    String author,
    String excerpt,
    String contentObjectKey,
    String contentUrl,
    long contentSize,
    String contentSha256,
    int ratingCount,
    BigDecimal ratingTotal,
    Integer myRating,
    Instant createdAt,
    Instant updatedAt) {

  public double averageRating() {
    if (ratingCount <= 0 || ratingTotal == null) {
      return 0;
    }
    return ratingTotal.doubleValue() / ratingCount;
  }
}
