package com.relay.backend.module.announcement.dto;

import java.time.Instant;

public record AnnouncementResponse(Long id, String title, String content, Instant publishedAt) {}
