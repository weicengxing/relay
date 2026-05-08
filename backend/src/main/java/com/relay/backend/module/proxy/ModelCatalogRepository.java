package com.relay.backend.module.proxy;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Arrays;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ModelCatalogRepository {

  private final JdbcTemplate jdbcTemplate;

  public ModelCatalogRepository(JdbcTemplate jdbcTemplate) {
    this.jdbcTemplate = jdbcTemplate;
  }

  public List<ModelCatalogItem> findEnabled() {
    return jdbcTemplate.query(
        """
        select id, name, provider, input_price, output_price, cached_input_price, cache_creation_price, tags
        from model_catalog
        where enabled = true
          and id in ('gpt-5.5', 'gpt-5.4', 'gpt-5.3-codex', 'gpt-5.4-mini')
        order by sort_order, id
        """,
        this::mapRow);
  }

  public java.util.Optional<ModelCatalogItem> findById(String id) {
    return jdbcTemplate
        .query(
            """
            select id, name, provider, input_price, output_price, cached_input_price, cache_creation_price, tags
            from model_catalog
            where enabled = true and id = ?
            """,
            this::mapRow,
            id)
        .stream()
        .findFirst();
  }

  private ModelCatalogItem mapRow(ResultSet rs, int rowNum) throws SQLException {
    return new ModelCatalogItem(
        rs.getString("id"),
        rs.getString("name"),
        rs.getString("provider"),
        rs.getBigDecimal("input_price"),
        rs.getBigDecimal("output_price"),
        rs.getBigDecimal("cached_input_price"),
        rs.getBigDecimal("cache_creation_price"),
        parseTags(rs.getString("tags")));
  }

  private List<String> parseTags(String tags) {
    if (tags == null || tags.isBlank()) {
      return List.of();
    }
    return Arrays.stream(tags.split(",")).map(String::trim).filter(tag -> !tag.isBlank()).toList();
  }
}
