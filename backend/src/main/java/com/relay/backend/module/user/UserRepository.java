package com.relay.backend.module.user;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class UserRepository {

  private final JdbcTemplate jdbcTemplate;

  public UserRepository(JdbcTemplate jdbcTemplate) {
    this.jdbcTemplate = jdbcTemplate;
  }

  public UserAccount create(
      UUID id, String email, String passwordHash, String registrationIp, Instant createdAt) {
    jdbcTemplate.update(
        """
        insert into users (id, email, password_hash, registration_ip, created_at)
        values (?, ?, ?, ?, ?)
        """,
        id,
        email,
        passwordHash,
        registrationIp,
        Timestamp.from(createdAt));

    return findByEmail(email).orElseThrow();
  }

  public Optional<UserAccount> findByEmail(String email) {
    return jdbcTemplate
        .query(
            """
            select id, email, password_hash, registration_ip, balance, status, created_at
            from users
            where email = ?
            """,
            this::mapRow,
            email)
        .stream()
        .findFirst();
  }

  private UserAccount mapRow(ResultSet rs, int rowNum) throws SQLException {
    return new UserAccount(
        rs.getObject("id", UUID.class),
        rs.getString("email"),
        rs.getString("password_hash"),
        rs.getString("registration_ip"),
        rs.getBigDecimal("balance"),
        rs.getString("status"),
        rs.getTimestamp("created_at").toInstant());
  }
}
