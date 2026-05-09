package com.relay.backend.module.webchat.history.dto;

import java.util.List;

public record ChatHistoryPageResponse(
    List<ChatHistoryFileResponse> items,
    int page,
    int size,
    int total,
    boolean hasMore) {}
