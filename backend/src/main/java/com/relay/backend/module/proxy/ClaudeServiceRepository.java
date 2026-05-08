package com.relay.backend.module.proxy;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ClaudeServiceRepository {

  private final JdbcTemplate jdbcTemplate;

  public ClaudeServiceRepository(JdbcTemplate jdbcTemplate) {
    this.jdbcTemplate = jdbcTemplate;
  }

  public List<ClaudeServiceConfig> findAll() {
    return jdbcTemplate.query(
        """
        select id, api_endpoint, token, concurrent_limit, created_at, updated_at
        from claude_services
        order by id
        """,
        this::mapRow);
  }

  private ClaudeServiceConfig mapRow(ResultSet rs, int rowNum) throws SQLException {
    return new ClaudeServiceConfig(
        rs.getLong("id"),
        rs.getString("api_endpoint"),
        rs.getString("token"),
        rs.getInt("concurrent_limit"),
        rs.getTimestamp("created_at").toInstant(),
        rs.getTimestamp("updated_at").toInstant());
  }
}
