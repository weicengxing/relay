package com.relay.backend.module.webchat;

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
public class WebChatRepository {

  private final JdbcTemplate jdbcTemplate;

  public WebChatRepository(JdbcTemplate jdbcTemplate) {
    this.jdbcTemplate = jdbcTemplate;
  }

  public List<WebChatModelConfig> findEnabledConfigs() {
    return jdbcTemplate.query(
        """
        select *
        from web_chat_model_configs
        where enabled = true
        order by id
        """,
        this::mapConfigRow);
  }

  public Optional<WebChatSession> findSession(UUID userId) {
    return jdbcTemplate
        .query(
            """
            select
              s.user_id,
              s.config_id,
              s.conversation_id,
              s.parent_message_id,
              s.updated_at as session_updated_at,
              c.id,
              c.name,
              c.base_url,
              c.model,
              c.auth_header,
              c.bearer_token,
              c.account_id,
              c.conduit_token,
              c.sentinel_token,
              c.cookie,
              c.oai_device_id,
              c.oai_session_id,
              c.oai_client_build_number,
              c.oai_client_version,
              c.oai_is,
              c.user_agent,
              c.call_prepare,
              c.enabled,
              c.created_at,
              c.updated_at
            from web_chat_user_sessions s
            join web_chat_model_configs c on c.id = s.config_id
            where s.user_id = ?
            """,
            this::mapSessionRow,
            userId)
        .stream()
        .findFirst();
  }

  public WebChatSession saveSession(
      UUID userId, Long configId, String conversationId, String parentMessageId, Instant updatedAt) {
    int updated =
        jdbcTemplate.update(
            """
            update web_chat_user_sessions
            set config_id = ?, conversation_id = ?, parent_message_id = ?, updated_at = ?
            where user_id = ?
            """,
            configId,
            blankToNull(conversationId),
            firstNonBlank(parentMessageId, "client-created-root"),
            Timestamp.from(updatedAt),
            userId);
    if (updated == 0) {
      try {
        jdbcTemplate.update(
            """
            insert into web_chat_user_sessions
              (user_id, config_id, conversation_id, parent_message_id, updated_at)
            values (?, ?, ?, ?, ?)
            """,
            userId,
            configId,
            blankToNull(conversationId),
            firstNonBlank(parentMessageId, "client-created-root"),
            Timestamp.from(updatedAt));
      } catch (DuplicateKeyException ignored) {
        jdbcTemplate.update(
            """
            update web_chat_user_sessions
            set config_id = ?, conversation_id = ?, parent_message_id = ?, updated_at = ?
            where user_id = ?
            """,
            configId,
            blankToNull(conversationId),
            firstNonBlank(parentMessageId, "client-created-root"),
            Timestamp.from(updatedAt),
            userId);
      }
    }
    return findSession(userId).orElseThrow();
  }

  public void updateConfigRuntimeState(Long configId, String oaiIs, Instant updatedAt) {
    if (configId == null || oaiIs == null || oaiIs.isBlank()) {
      return;
    }
    jdbcTemplate.update(
        """
        update web_chat_model_configs
        set oai_is = ?, updated_at = ?
        where id = ?
        """,
        oaiIs,
        Timestamp.from(updatedAt),
        configId);
  }

  private WebChatSession mapSessionRow(ResultSet rs, int rowNum) throws SQLException {
    return new WebChatSession(
        rs.getObject("user_id", UUID.class),
        rs.getLong("config_id"),
        rs.getString("conversation_id"),
        rs.getString("parent_message_id"),
        toInstant(rs.getTimestamp("session_updated_at")),
        mapConfigRow(rs, rowNum));
  }

  private WebChatModelConfig mapConfigRow(ResultSet rs, int rowNum) throws SQLException {
    return new WebChatModelConfig(
        rs.getLong("id"),
        rs.getString("name"),
        rs.getString("base_url"),
        rs.getString("model"),
        rs.getString("auth_header"),
        rs.getString("bearer_token"),
        rs.getString("account_id"),
        rs.getString("conduit_token"),
        rs.getString("sentinel_token"),
        rs.getString("cookie"),
        rs.getString("oai_device_id"),
        rs.getString("oai_session_id"),
        rs.getString("oai_client_build_number"),
        rs.getString("oai_client_version"),
        rs.getString("oai_is"),
        rs.getString("user_agent"),
        rs.getBoolean("call_prepare"),
        rs.getBoolean("enabled"),
        toInstant(rs.getTimestamp("created_at")),
        toInstant(rs.getTimestamp("updated_at")));
  }

  private Instant toInstant(Timestamp timestamp) {
    return timestamp == null ? null : timestamp.toInstant();
  }

  private String blankToNull(String value) {
    return value == null || value.isBlank() ? null : value;
  }

  private String firstNonBlank(String first, String second) {
    return first == null || first.isBlank() ? second : first;
  }
}
