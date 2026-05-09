package com.relay.backend.module.novel.dto;

import java.time.Instant;

public record NovelResponse(
    Long id,
    String title,
    String author,
    String content,
    String contentUrl,
    double averageRating,
    int ratingCount,
    Integer myRating,
    Instant createdAt,
    Instant updatedAt) {}
