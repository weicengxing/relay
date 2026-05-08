package com.relay.backend.module.announcement;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class AnnouncementRepository {

  private static final String BADGE_DEFAULT_KEY = "announcements.badge_default";

  private final JdbcTemplate jdbcTemplate;

  public AnnouncementRepository(JdbcTemplate jdbcTemplate) {
    this.jdbcTemplate = jdbcTemplate;
  }

  public List<AnnouncementRecord> findActive() {
    return jdbcTemplate.query(
        """
        select id, title, content, published_at, created_at, updated_at
        from announcements
        where active = true
        order by published_at desc, id desc
        """,
        this::mapRow);
  }

  public int countUnread(UUID userId) {
    Integer count =
        jdbcTemplate.queryForObject(
            """
            select count(*)
            from announcements a
            left join announcement_user_state s on s.user_id = ?
            where a.active = true
              and (s.last_seen_at is null or a.published_at > s.last_seen_at)
            """,
            Integer.class,
            userId);
    return count == null ? 0 : count;
  }

  public void markSeen(UUID userId, Instant seenAt) {
    int updated =
        jdbcTemplate.update(
            """
            update announcement_user_state
            set last_seen_at = ?, updated_at = ?
            where user_id = ?
            """,
            Timestamp.from(seenAt),
            Timestamp.from(seenAt),
            userId);
    if (updated == 0) {
      try {
        jdbcTemplate.update(
            """
            insert into announcement_user_state (user_id, last_seen_at, updated_at)
            values (?, ?, ?)
            """,
            userId,
            Timestamp.from(seenAt),
            Timestamp.from(seenAt));
      } catch (DuplicateKeyException ignored) {
        jdbcTemplate.update(
            """
            update announcement_user_state
            set last_seen_at = ?, updated_at = ?
            where user_id = ?
            """,
            Timestamp.from(seenAt),
            Timestamp.from(seenAt),
            userId);
      }
    }
  }

  public int badgeDefault() {
    Optional<String> value =
        jdbcTemplate
            .query(
                """
                select setting_value
                from app_settings
                where setting_key = ?
                """,
                (rs, rowNum) -> rs.getString("setting_value"),
                BADGE_DEFAULT_KEY)
            .stream()
            .findFirst();
    return value.map(this::positiveInt).orElse(0);
  }

  private int positiveInt(String value) {
    if (value == null || value.isBlank()) {
      return 0;
    }
    try {
      return Math.max(0, Integer.parseInt(value.trim()));
    } catch (NumberFormatException exception) {
      return 0;
    }
  }

  private AnnouncementRecord mapRow(ResultSet rs, int rowNum) throws SQLException {
    return new AnnouncementRecord(
        rs.getLong("id"),
        rs.getString("title"),
        rs.getString("content"),
        toInstant(rs.getTimestamp("published_at")),
        toInstant(rs.getTimestamp("created_at")),
        toInstant(rs.getTimestamp("updated_at")));
  }

  private Instant toInstant(Timestamp timestamp) {
    return timestamp == null ? null : timestamp.toInstant();
  }
}
