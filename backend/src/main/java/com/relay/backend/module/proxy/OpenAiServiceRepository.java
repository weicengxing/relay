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
        this::mapRow,
        apiEndpoint,
        token);
  }

  private OpenAiServiceConfig mapRow(ResultSet rs, int rowNum) throws SQLException {
    return new OpenAiServiceConfig(
        rs.getLong("id"),
        rs.getString("api_endpoint"),
        rs.getString("token"),
        rs.getTimestamp("created_at").toInstant(),
        rs.getTimestamp("updated_at").toInstant());
  }
}

