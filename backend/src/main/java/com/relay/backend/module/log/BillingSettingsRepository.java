package com.relay.backend.module.log;

import java.math.BigDecimal;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class BillingSettingsRepository {

  private static final Logger log = LoggerFactory.getLogger(BillingSettingsRepository.class);
  static final BigDecimal DEFAULT_COST_MULTIPLIER = new BigDecimal("1.2");

  private final JdbcTemplate jdbcTemplate;

  public BillingSettingsRepository(JdbcTemplate jdbcTemplate) {
    this.jdbcTemplate = jdbcTemplate;
  }

  public BigDecimal costMultiplier() {
    try {
      String value =
          jdbcTemplate.query(
              """
              select setting_value
              from app_settings
              where setting_key = 'billing.cost_multiplier'
              """,
              rs -> rs.next() ? rs.getString("setting_value") : null);
      return positiveDecimal(value, DEFAULT_COST_MULTIPLIER);
    } catch (DataAccessException exception) {
      log.warn("Unable to load billing cost multiplier; using default", exception);
      return DEFAULT_COST_MULTIPLIER;
    }
  }

  private BigDecimal positiveDecimal(String value, BigDecimal fallback) {
    if (value == null || value.isBlank()) {
      return fallback;
    }
    try {
      BigDecimal parsed = new BigDecimal(value.trim());
      return parsed.signum() > 0 ? parsed : fallback;
    } catch (NumberFormatException exception) {
      return fallback;
    }
  }
}
