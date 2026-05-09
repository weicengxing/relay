package com.relay.backend.module.novel.dto;

import java.time.Instant;

public record NovelSummaryResponse(
    Long id,
    String title,
    String author,
    String excerpt,
    double averageRating,
    int ratingCount,
    Integer myRating,
    Instant createdAt) {}
