package com.relay.backend.module.novel.dto;

import java.util.List;

public record NovelPageResponse(
    List<NovelSummaryResponse> items,
    int page,
    int size,
    int total,
    int totalRatings,
    boolean hasMore) {}
