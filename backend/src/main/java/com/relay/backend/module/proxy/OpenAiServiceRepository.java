package com.relay.backend.module.proxy;

import java.sql.ResultSet;
import java.sql.SQLException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OpenAiServiceRepository {

  private final JdbcTemplate jdbcTemplate;

  public OpenAiServiceRepository(JdbcTemplate jdbcTemplate) {
    this.jdbcTemplate = jdbcTemplate;
  }

  public OpenAiServiceConfig save(String apiEndpoint, String token) {
    return jdbcTemplate.queryForObject(
        """
        insert into openai_services (api_endpoint, token)
        values (?, ?)
        returning id, api_endpoint, token, created_at, updated_at
        """,
        this::mapServiceRow,
        apiEndpoint,
        token);
  }

  public java.util.List<OpenAiServiceConfig> findAll() {
    return jdbcTemplate.query(
        """
        select
          s.id,
          s.api_endpoint,
          s.token,
          s.created_at,
          s.updated_at,
          p.id as profile_id,
          p.profile_name,
          p.auth_mode,
          p.openai_api_key,
          p.access_token,
          p.account_id,
          p.id_token,
          p.refresh_token,
          p.client_id,
          p.base_url,
          p.model,
          p.reasoning_effort,
          p.last_refresh,
          p.created_at as profile_created_at,
          p.updated_at as profile_updated_at
        from openai_services s
        left join openai_codex_profiles p on p.openai_service_id = s.id
        order by s.id
        """,
        this::mapRow);
  }

  private OpenAiServiceConfig mapRow(ResultSet rs, int rowNum) throws SQLException {
    Long profileId = rs.getObject("profile_id", Long.class);
    return new OpenAiServiceConfig(
        rs.getLong("id"),
        rs.getString("api_endpoint"),
        rs.getString("token"),
        profileId == null ? null : mapCodexProfile(rs, profileId),
        rs.getTimestamp("created_at").toInstant(),
        rs.getTimestamp("updated_at").toInstant());
  }

  private OpenAiServiceConfig mapServiceRow(ResultSet rs, int rowNum) throws SQLException {
    return new OpenAiServiceConfig(
        rs.getLong("id"),
        rs.getString("api_endpoint"),
        rs.getString("token"),
        null,
        rs.getTimestamp("created_at").toInstant(),
        rs.getTimestamp("updated_at").toInstant());
  }

  private CodexProfileConfig mapCodexProfile(ResultSet rs, Long profileId) throws SQLException {
    return new CodexProfileConfig(
        profileId,
        rs.getLong("id"),
        rs.getString("profile_name"),
        rs.getString("auth_mode"),
        rs.getString("openai_api_key"),
        rs.getString("access_token"),
        rs.getString("account_id"),
        rs.getString("id_token"),
        rs.getString("refresh_token"),
        rs.getString("client_id"),
        rs.getString("base_url"),
        rs.getString("model"),
        rs.getString("reasoning_effort"),
        rs.getTimestamp("last_refresh") == null ? null : rs.getTimestamp("last_refresh").toInstant(),
        rs.getTimestamp("profile_created_at").toInstant(),
        rs.getTimestamp("profile_updated_at").toInstant());
  }
}
