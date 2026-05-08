package com.relay.backend.module.apikey;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class ApiKeyRepository {

  private final JdbcTemplate jdbcTemplate;

  public ApiKeyRepository(JdbcTemplate jdbcTemplate) {
    this.jdbcTemplate = jdbcTemplate;
  }

  public ApiKeyRecord create(UUID userId, String keyHash, String keyValue, String name) {
    KeyHolder keyHolder = new GeneratedKeyHolder();
    jdbcTemplate.update(
        connection -> {
          PreparedStatement statement =
              connection.prepareStatement(
                  """
                  insert into api_keys (user_id, key_hash, key_value, name)
                  values (?, ?, ?, ?)
                  """,
                  new String[] {"id"});
          statement.setObject(1, userId);
          statement.setString(2, keyHash);
          statement.setString(3, keyValue);
          statement.setString(4, name);
          return statement;
        },
        keyHolder);

    Number id = keyHolder.getKey();
    if (id == null) {
      throw new IllegalStateException("Unable to read generated API key id");
    }

    return findById(id.longValue()).orElseThrow();
  }

  public Optional<ApiKeyRecord> findById(Long id) {
    return jdbcTemplate
        .query(
            """
            select user_id, id, key_hash, key_value, name, status, created_at
            from api_keys
            where id = ?
            """,
            this::mapRow,
            id)
        .stream()
        .findFirst();
  }

  public List<ApiKeyRecord> findActiveByUserId(UUID userId) {
    return jdbcTemplate.query(
        """
        select user_id, id, key_hash, key_value, name, status, created_at
        from api_keys
        where user_id = ? and status <> 'revoked'
        order by created_at desc
        """,
        this::mapRow,
        userId);
  }

  public Optional<ApiKeyRecord> findActiveByHash(String keyHash) {
    return jdbcTemplate
        .query(
            """
            select user_id, id, key_hash, key_value, name, status, created_at
            from api_keys
            where key_hash = ? and status = 'active'
            """,
            this::mapRow,
            keyHash)
        .stream()
        .findFirst();
  }

  public boolean revoke(UUID userId, Long id) {
    int updated =
        jdbcTemplate.update(
            """
            update api_keys
            set status = 'revoked'
            where id = ? and user_id = ? and status <> 'revoked'
            """,
            id,
            userId);
    return updated > 0;
  }

  public boolean existsActiveHash(String keyHash) {
    Integer count =
        jdbcTemplate.queryForObject(
            """
            select count(*)
            from api_keys
            where key_hash = ? and status = 'active'
            """,
            Integer.class,
            keyHash);
    return count != null && count > 0;
  }

  private ApiKeyRecord mapRow(ResultSet rs, int rowNum) throws SQLException {
    return new ApiKeyRecord(
        rs.getObject("user_id", UUID.class),
        rs.getLong("id"),
        rs.getString("key_hash"),
        rs.getString("key_value"),
        rs.getString("name"),
        rs.getString("status"),
        rs.getTimestamp("created_at").toInstant());
  }
}
