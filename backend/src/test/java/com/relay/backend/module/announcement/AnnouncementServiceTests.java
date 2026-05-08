package com.relay.backend.module.announcement;

import static org.assertj.core.api.Assertions.assertThat;

import com.relay.backend.test.RedisTestConfig;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@ActiveProfiles("test")
@Transactional
@org.springframework.context.annotation.Import(RedisTestConfig.class)
class AnnouncementServiceTests {

  @Autowired private AnnouncementService announcementService;
  @Autowired private JdbcTemplate jdbcTemplate;

  @Test
  void markReadClearsBadgeOnlyForCurrentUser() {
    UUID userA = UUID.randomUUID();
    UUID userB = UUID.randomUUID();
    insertUser(userA, "a@example.com", "10.0.10.1");
    insertUser(userB, "b@example.com", "10.0.10.2");
    jdbcTemplate.update(
        "update app_settings set setting_value = '5' where setting_key = 'announcements.badge_default'");
    insertAnnouncement("First notice", "One", "2026-05-08T01:00:00Z");
    insertAnnouncement("Second notice", "Two", "2026-05-08T02:00:00Z");

    var beforeA = announcementService.inbox(userA);
    assertThat(beforeA.announcements()).hasSize(2);
    assertThat(beforeA.unreadCount()).isEqualTo(2);
    assertThat(beforeA.badgeCount()).isEqualTo(5);

    var afterA = announcementService.markRead(userA);
    assertThat(afterA.unreadCount()).isZero();
    assertThat(afterA.badgeCount()).isZero();

    var beforeB = announcementService.inbox(userB);
    assertThat(beforeB.unreadCount()).isEqualTo(2);
    assertThat(beforeB.badgeCount()).isEqualTo(5);

    insertAnnouncement("New notice", "Three", Instant.now().plusSeconds(60).toString());
    var afterNewAnnouncementA = announcementService.inbox(userA);
    assertThat(afterNewAnnouncementA.unreadCount()).isEqualTo(1);
    assertThat(afterNewAnnouncementA.badgeCount()).isEqualTo(5);
  }

  private void insertUser(UUID id, String email, String ip) {
    jdbcTemplate.update(
        """
        insert into users (id, email, password_hash, registration_ip)
        values (?, ?, ?, ?)
        """,
        id,
        email,
        "hash",
        ip);
  }

  private void insertAnnouncement(String title, String content, String publishedAt) {
    Instant instant = Instant.parse(publishedAt);
    jdbcTemplate.update(
        """
        insert into announcements (title, content, published_at)
        values (?, ?, ?)
        """,
        title,
        content,
        Timestamp.from(instant));
  }
}
