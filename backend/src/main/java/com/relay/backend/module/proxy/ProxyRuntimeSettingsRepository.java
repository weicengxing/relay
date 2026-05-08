package com.relay.backend.module.proxy;

import java.util.Map;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProxyRuntimeSettingsRepository {

  private static final Logger log = LoggerFactory.getLogger(ProxyRuntimeSettingsRepository.class);
  private static final int DEFAULT_OPENAI_REQUEST_MODE = 1;
  private static final int DEFAULT_OPENAI_CONCURRENT_LIMIT = 20;

  private final JdbcTemplate jdbcTemplate;

  public ProxyRuntimeSettingsRepository(JdbcTemplate jdbcTemplate) {
    this.jdbcTemplate = jdbcTemplate;
  }

  public ProxyRuntimeSettings current() {
    try {
      Map<String, String> values =
          jdbcTemplate
              .query(
                  """
                  select setting_key, setting_value
                  from app_settings
                  where setting_key in ('openai.request_mode', 'openai.concurrent_limit')
                  """,
                  (rs, rowNum) -> Map.entry(rs.getString("setting_key"), rs.getString("setting_value")))
              .stream()
              .collect(Collectors.toMap(Map.Entry::getKey, Map.Entry::getValue, (first, ignored) -> first));
      return new ProxyRuntimeSettings(
          requestMode(values.get("openai.request_mode")),
          positiveInt(values.get("openai.concurrent_limit"), DEFAULT_OPENAI_CONCURRENT_LIMIT));
    } catch (DataAccessException exception) {
      log.warn("Unable to load proxy runtime settings; using defaults", exception);
      return defaults();
    }
  }

  private ProxyRuntimeSettings defaults() {
    return new ProxyRuntimeSettings(DEFAULT_OPENAI_REQUEST_MODE, DEFAULT_OPENAI_CONCURRENT_LIMIT);
  }

  private int requestMode(String value) {
    int parsed = positiveInt(value, DEFAULT_OPENAI_REQUEST_MODE);
    return parsed == 2 ? 2 : DEFAULT_OPENAI_REQUEST_MODE;
  }

  private int positiveInt(String value, int fallback) {
    if (value == null || value.isBlank()) {
      return fallback;
    }
    try {
      int parsed = Integer.parseInt(value.trim());
      return parsed > 0 ? parsed : fallback;
    } catch (NumberFormatException exception) {
      return fallback;
    }
  }
}
