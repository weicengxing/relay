package com.relay.backend.module.announcement.dto;

import java.util.List;

public record AnnouncementInboxResponse(
    List<AnnouncementResponse> announcements, int unreadCount, int badgeCount) {}
