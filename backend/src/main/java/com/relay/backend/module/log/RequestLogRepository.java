package com.relay.backend.module.log;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class RequestLogRepository {

  private final JdbcTemplate jdbcTemplate;

  public RequestLogRepository(JdbcTemplate jdbcTemplate) {
    this.jdbcTemplate = jdbcTemplate;
  }

  public void save(RequestLogRecord log) {
    jdbcTemplate.update(
        """
        insert into request_logs (
          user_id, api_key_id, token_name, group_key, request_type, client_type, model,
          use_time_ms, first_token_ms, prompt_tokens, completion_tokens,
          cache_read_tokens, cache_creation_tokens, cost, ip, status, upstream_service_id, detail, created_at
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        log.userId(),
        log.apiKeyId(),
        log.tokenName(),
        log.groupKey(),
        log.requestType(),
        log.clientType(),
        log.model(),
        log.useTimeMs(),
        log.firstTokenMs(),
        log.promptTokens(),
        log.completionTokens(),
        log.cacheReadTokens(),
        log.cacheCreationTokens(),
        log.cost(),
        log.ip(),
        log.status(),
        log.upstreamServiceId(),
        log.detail(),
        Timestamp.from(log.createdAt()));
  }

  public List<RequestLogRecord> findRecentByUserId(UUID userId, Instant cursorCreatedAt, Long cursorId, int limit) {
    List<Object> args = new ArrayList<>();
    args.add(userId);

    String cursorClause = "";
    if (cursorCreatedAt != null && cursorId != null) {
      cursorClause = "and (created_at < ? or (created_at = ? and id < ?))";
      Timestamp cursorTimestamp = Timestamp.from(cursorCreatedAt);
      args.add(cursorTimestamp);
      args.add(cursorTimestamp);
      args.add(cursorId);
    }
    args.add(limit);

    return jdbcTemplate.query(
        """
        select id, user_id, api_key_id, token_name, group_key, request_type, client_type, model,
               use_time_ms, first_token_ms, prompt_tokens, completion_tokens,
               cache_read_tokens, cache_creation_tokens, cost, ip, status, upstream_service_id, detail, created_at
        from request_logs
        where user_id = ?
        %s
        order by created_at desc, id desc
        limit ?
        """
            .formatted(cursorClause),
        this::mapRow,
        args.toArray());
  }

  private RequestLogRecord mapRow(ResultSet rs, int rowNum) throws SQLException {
    return new RequestLogRecord(
        rs.getLong("id"),
        rs.getObject("user_id", UUID.class),
        rs.getLong("api_key_id"),
        rs.getString("token_name"),
        rs.getString("group_key"),
        rs.getString("request_type"),
        rs.getString("client_type"),
        rs.getString("model"),
        rs.getInt("use_time_ms"),
        rs.getInt("first_token_ms"),
        rs.getInt("prompt_tokens"),
        rs.getInt("completion_tokens"),
        rs.getInt("cache_read_tokens"),
        rs.getInt("cache_creation_tokens"),
        rs.getBigDecimal("cost"),
        rs.getString("ip"),
        rs.getString("status"),
        rs.getObject("upstream_service_id", Long.class),
        rs.getString("detail"),
        rs.getTimestamp("created_at").toInstant());
  }
}
