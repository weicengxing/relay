package com.relay.backend.module.announcement;

import com.relay.backend.module.announcement.dto.AnnouncementInboxResponse;
import com.relay.backend.module.announcement.dto.AnnouncementResponse;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AnnouncementService {

  private final AnnouncementRepository announcementRepository;

  public AnnouncementService(AnnouncementRepository announcementRepository) {
    this.announcementRepository = announcementRepository;
  }

  @Transactional(readOnly = true)
  public AnnouncementInboxResponse inbox(UUID userId) {
    List<AnnouncementResponse> announcements =
        announcementRepository.findActive().stream()
            .map(
                announcement ->
                    new AnnouncementResponse(
                        announcement.id(),
                        announcement.title(),
                        announcement.content(),
                        announcement.publishedAt()))
            .toList();
    int unreadCount = announcementRepository.countUnread(userId);
    int badgeDefault = announcementRepository.badgeDefault();
    int badgeCount = unreadCount == 0 ? 0 : Math.max(unreadCount, badgeDefault);
    return new AnnouncementInboxResponse(announcements, unreadCount, badgeCount);
  }

  @Transactional
  public AnnouncementInboxResponse markRead(UUID userId) {
    announcementRepository.markSeen(userId, Instant.now());
    return inbox(userId);
  }
}
