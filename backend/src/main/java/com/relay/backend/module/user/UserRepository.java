package com.relay.backend.module.user;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.math.BigDecimal;
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
      UUID id,
      String email,
      String passwordHash,
      String registrationIp,
      BigDecimal initialBalance,
      Instant createdAt) {
    jdbcTemplate.update(
        """
        insert into users (id, email, password_hash, registration_ip, balance, created_at)
        values (?, ?, ?, ?, ?, ?)
        """,
        id,
        email,
        passwordHash,
        registrationIp,
        initialBalance,
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

  public Optional<UserAccount> findById(UUID id) {
    return jdbcTemplate
        .query(
            """
            select id, email, password_hash, registration_ip, balance, status, created_at
            from users
            where id = ?
            """,
            this::mapRow,
            id)
        .stream()
        .findFirst();
  }

  public BigDecimal addBalance(UUID userId, BigDecimal amount) {
    return jdbcTemplate.queryForObject(
        """
        update users
        set balance = balance + ?
        where id = ?
        returning balance
        """,
        BigDecimal.class,
        amount,
        userId);
  }

  public BigDecimal deductBalance(UUID userId, BigDecimal amount) {
    return addBalance(userId, amount.negate());
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
