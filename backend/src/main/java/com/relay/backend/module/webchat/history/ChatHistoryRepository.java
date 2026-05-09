package com.relay.backend.module.webchat.history;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ChatHistoryRepository {

  private final JdbcTemplate jdbcTemplate;

  public ChatHistoryRepository(JdbcTemplate jdbcTemplate) {
    this.jdbcTemplate = jdbcTemplate;
    ensureSchema();
  }

  public Optional<ChatHistoryFile> findLatest(UUID userId) {
    return jdbcTemplate
        .query(
            """
            select *
            from web_chat_history_files
            where user_id = ?
            order by sequence desc
            limit 1
            """,
            this::mapRow,
            userId)
        .stream()
        .findFirst();
  }

  public Optional<ChatHistoryFile> findById(UUID userId, Long id) {
    return jdbcTemplate
        .query(
            """
            select *
            from web_chat_history_files
            where user_id = ? and id = ?
            """,
            this::mapRow,
            userId,
            id)
        .stream()
        .findFirst();
  }

  public List<ChatHistoryFile> findPage(UUID userId, int limit, int offset) {
    return jdbcTemplate.query(
        """
        select *
        from web_chat_history_files
        where user_id = ?
        order by updated_at desc, sequence desc
        limit ? offset ?
        """,
        this::mapRow,
        userId,
        limit,
        offset);
  }

  public int count(UUID userId) {
    Integer count =
        jdbcTemplate.queryForObject(
            "select count(*) from web_chat_history_files where user_id = ?",
            Integer.class,
            userId);
    return count == null ? 0 : count;
  }

  public ChatHistoryFile create(UUID userId, int sequence, String objectKey) {
    Instant now = Instant.now();
    return jdbcTemplate
        .query(
            """
            insert into web_chat_history_files
              (user_id, sequence, object_key, content_url, size_bytes, turn_count, created_at, updated_at)
            values (?, ?, ?, '', 0, 0, ?, ?)
            returning *
            """,
            this::mapRow,
            userId,
            sequence,
            objectKey,
            Timestamp.from(now),
            Timestamp.from(now))
        .stream()
        .findFirst()
        .orElseThrow();
  }

  public ChatHistoryFile updateAfterWrite(Long id, String contentUrl, long sizeBytes, int turnCount) {
    return jdbcTemplate
        .query(
            """
            update web_chat_history_files
            set content_url = ?, size_bytes = ?, turn_count = ?, updated_at = ?
            where id = ?
            returning *
            """,
            this::mapRow,
            contentUrl == null ? "" : contentUrl,
            sizeBytes,
            turnCount,
            Timestamp.from(Instant.now()),
            id)
        .stream()
        .findFirst()
        .orElseThrow();
  }

  private ChatHistoryFile mapRow(ResultSet rs, int rowNum) throws SQLException {
    return new ChatHistoryFile(
        rs.getLong("id"),
        rs.getObject("user_id", UUID.class),
        rs.getInt("sequence"),
        rs.getString("object_key"),
        rs.getString("content_url"),
        rs.getLong("size_bytes"),
        rs.getInt("turn_count"),
        toInstant(rs.getTimestamp("created_at")),
        toInstant(rs.getTimestamp("updated_at")));
  }

  private Instant toInstant(Timestamp timestamp) {
    return timestamp == null ? null : timestamp.toInstant();
  }

  private void ensureSchema() {
    jdbcTemplate.execute(
        """
        create table if not exists web_chat_history_files (
          id bigserial primary key,
          user_id uuid not null references users(id) on delete cascade,
          sequence int not null,
          object_key text not null,
          content_url text not null default '',
          size_bytes bigint not null default 0,
          turn_count int not null default 0,
          created_at timestamp with time zone not null default now(),
          updated_at timestamp with time zone not null default now(),
          unique (user_id, sequence)
        )
        """);
    jdbcTemplate.execute(
        """
        create index if not exists idx_web_chat_history_files_user_updated
          on web_chat_history_files(user_id, updated_at desc)
        """);
  }
}
