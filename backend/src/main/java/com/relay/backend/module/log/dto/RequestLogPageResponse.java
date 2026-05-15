package com.relay.backend.module.log.dto;

import java.util.List;

public record RequestLogPageResponse(
    List<RequestLogResponse> items,
    int limit,
    boolean hasMore,
    String nextCursor) {}
