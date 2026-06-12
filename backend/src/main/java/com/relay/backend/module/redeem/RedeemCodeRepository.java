package com.relay.backend.module.redeem;

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
public class RedeemCodeRepository {

  private final JdbcTemplate jdbcTemplate;

  public RedeemCodeRepository(JdbcTemplate jdbcTemplate) {
    this.jdbcTemplate = jdbcTemplate;
  }

  public Optional<RedeemCodeRecord> findByCodeForUpdate(String code) {
    return jdbcTemplate
        .query(
            """
            select id, code, amount, expires_at, holder_user_id, redeemed_at,
                   batch, redeemed_ip, expired_deducted_at, created_at, updated_at
            from redeem_codes
            where code = ?
            for update
            """,
            this::mapRow,
            code)
        .stream()
        .findFirst();
  }

  public Optional<RedeemCodeRecord> findByIdForUpdate(Long id) {
    return jdbcTemplate
        .query(
            """
            select id, code, amount, expires_at, holder_user_id, redeemed_at,
                   batch, redeemed_ip, expired_deducted_at, created_at, updated_at
            from redeem_codes
            where id = ?
            for update
            """,
            this::mapRow,
            id)
        .stream()
        .findFirst();
  }

  public boolean hasUserRedeemedBatch(UUID userId, String batch) {
    Integer count =
        jdbcTemplate.queryForObject(
            """
            select count(*)
            from redeem_codes
            where holder_user_id = ? and batch = ?
            """,
            Integer.class,
            userId,
            batch);
    return count != null && count > 0;
  }

  public boolean hasIpRedeemedBatch(String redeemedIp, String batch) {
    if (redeemedIp == null || redeemedIp.isBlank()) {
      return false;
    }
    Integer count =
        jdbcTemplate.queryForObject(
            """
            select count(*)
            from redeem_codes
            where redeemed_ip = ? and batch = ?
            """,
            Integer.class,
            redeemedIp,
            batch);
    return count != null && count > 0;
  }

  public RedeemCodeRecord markRedeemed(Long id, UUID userId, String redeemedIp, Instant redeemedAt) {
    return jdbcTemplate.queryForObject(
        """
        update redeem_codes
        set holder_user_id = ?, redeemed_ip = ?, redeemed_at = ?, updated_at = ?
        where id = ? and holder_user_id is null
        returning id, code, amount, expires_at, holder_user_id, redeemed_at,
                  batch, redeemed_ip, expired_deducted_at, created_at, updated_at
        """,
        this::mapRow,
        userId,
        redeemedIp,
        Timestamp.from(redeemedAt),
        Timestamp.from(redeemedAt),
        id);
  }

  public void markExpiredDeducted(Long id, Instant deductedAt) {
    jdbcTemplate.update(
        """
        update redeem_codes
        set expired_deducted_at = ?, updated_at = ?
        where id = ? and expired_deducted_at is null
        """,
        Timestamp.from(deductedAt),
        Timestamp.from(deductedAt),
        id);
  }

  public List<RedeemCodeRecord> findPendingExpirations() {
    return jdbcTemplate.query(
        """
        select id, code, amount, expires_at, holder_user_id, redeemed_at,
               batch, redeemed_ip, expired_deducted_at, created_at, updated_at
        from redeem_codes
        where holder_user_id is not null and expired_deducted_at is null
        order by expires_at
        """,
        this::mapRow);
  }

  private RedeemCodeRecord mapRow(ResultSet rs, int rowNum) throws SQLException {
    return new RedeemCodeRecord(
        rs.getLong("id"),
        rs.getString("code"),
        rs.getString("batch"),
        rs.getBigDecimal("amount"),
        rs.getTimestamp("expires_at").toInstant(),
        rs.getObject("holder_user_id", UUID.class),
        rs.getString("redeemed_ip"),
        toInstant(rs.getTimestamp("redeemed_at")),
        toInstant(rs.getTimestamp("expired_deducted_at")),
        rs.getTimestamp("created_at").toInstant(),
        rs.getTimestamp("updated_at").toInstant());
  }

  private Instant toInstant(Timestamp timestamp) {
    return timestamp == null ? null : timestamp.toInstant();
  }
}
