package com.relay.backend.module.announcement;

import java.time.Instant;

public record AnnouncementRecord(
    Long id,
    String title,
    String content,
    Instant publishedAt,
    Instant createdAt,
    Instant updatedAt) {}
