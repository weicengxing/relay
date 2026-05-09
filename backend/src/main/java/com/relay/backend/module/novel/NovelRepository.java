package com.relay.backend.module.novel;

import java.math.BigDecimal;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class NovelRepository {

  private final JdbcTemplate jdbcTemplate;

  public NovelRepository(JdbcTemplate jdbcTemplate) {
    this.jdbcTemplate = jdbcTemplate;
  }

  public NovelRecord create(
      UUID userId,
      String title,
      String author,
      String excerpt,
      NovelStorageObject storageObject) {
    KeyHolder keyHolder = new GeneratedKeyHolder();
    jdbcTemplate.update(
        connection -> {
          PreparedStatement statement =
              connection.prepareStatement(
                  """
                  insert into novels (
                    user_id, title, author, excerpt, content_object_key,
                    content_url, content_size, content_sha256
                  )
                  values (?, ?, ?, ?, ?, ?, ?, ?)
                  """,
                  new String[] {"id"});
          statement.setObject(1, userId);
          statement.setString(2, title);
          statement.setString(3, author);
          statement.setString(4, excerpt);
          statement.setString(5, storageObject.objectKey());
          statement.setString(6, storageObject.url());
          statement.setLong(7, storageObject.size());
          statement.setString(8, storageObject.sha256());
          return statement;
        },
        keyHolder);

    Number id = keyHolder.getKey();
    if (id == null) {
      throw new IllegalStateException("Unable to read generated novel id");
    }
    return findById(id.longValue(), userId).orElseThrow();
  }

  public List<NovelRecord> findAll(UUID viewerUserId) {
    return jdbcTemplate.query(
        """
        select n.id, n.user_id, n.title, n.author, n.excerpt, n.content_object_key,
               n.content_url, n.content_size, n.content_sha256, n.rating_count, n.rating_total,
               r.score as my_rating, n.created_at, n.updated_at
        from novels n
        left join novel_ratings r on r.novel_id = n.id and r.user_id = ?
        order by n.created_at desc, n.id desc
        """,
        this::mapRow,
        viewerUserId);
  }

  public Optional<NovelRecord> findById(Long id, UUID viewerUserId) {
    return jdbcTemplate
        .query(
            """
            select n.id, n.user_id, n.title, n.author, n.excerpt, n.content_object_key,
                   n.content_url, n.content_size, n.content_sha256, n.rating_count, n.rating_total,
                   r.score as my_rating, n.created_at, n.updated_at
            from novels n
            left join novel_ratings r on r.novel_id = n.id and r.user_id = ?
            where n.id = ?
            """,
            this::mapRow,
            viewerUserId,
            id)
        .stream()
        .findFirst();
  }

  public List<NovelRecord> findByIds(List<Long> ids, UUID viewerUserId) {
    if (ids == null || ids.isEmpty()) {
      return List.of();
    }
    String placeholders = String.join(",", ids.stream().map(ignored -> "?").toList());
    Object[] args = new Object[ids.size() + 1];
    args[0] = viewerUserId;
    for (int i = 0; i < ids.size(); i++) {
      args[i + 1] = ids.get(i);
    }
    return jdbcTemplate.query(
        """
        select n.id, n.user_id, n.title, n.author, n.excerpt, n.content_object_key,
               n.content_url, n.content_size, n.content_sha256, n.rating_count, n.rating_total,
               r.score as my_rating, n.created_at, n.updated_at
        from novels n
        left join novel_ratings r on r.novel_id = n.id and r.user_id = ?
        where n.id in (%s)
        """
            .formatted(placeholders),
        this::mapRow,
        args);
  }

  public List<NovelRecord> findTopByRating(UUID viewerUserId, int limit) {
    return jdbcTemplate.query(
        """
        select n.id, n.user_id, n.title, n.author, n.excerpt, n.content_object_key,
               n.content_url, n.content_size, n.content_sha256, n.rating_count, n.rating_total,
               r.score as my_rating, n.created_at, n.updated_at
        from novels n
        left join novel_ratings r on r.novel_id = n.id and r.user_id = ?
        order by case when n.rating_count = 0 then 0 else n.rating_total / n.rating_count end desc,
                 n.rating_count desc,
                 n.created_at desc
        limit ?
        """,
        this::mapRow,
        viewerUserId,
        limit);
  }

  public Map<String, Double> findLeaderboardScores() {
    Map<String, Double> scores = new LinkedHashMap<>();
    jdbcTemplate
        .query(
            """
            select id, rating_count, rating_total
            from novels
            """,
            (rs, rowNum) ->
                Map.entry(
                    String.valueOf(rs.getLong("id")),
                    average(rs.getInt("rating_count"), rs.getBigDecimal("rating_total"))))
        .forEach(entry -> scores.put(entry.getKey(), entry.getValue()));
    return scores;
  }

  public Optional<Integer> findRating(Long novelId, UUID userId) {
    return jdbcTemplate
        .query(
            """
            select score
            from novel_ratings
            where novel_id = ? and user_id = ?
            """,
            (rs, rowNum) -> rs.getInt("score"),
            novelId,
            userId)
        .stream()
        .findFirst();
  }

  public boolean exists(Long id) {
    Integer count =
        jdbcTemplate.queryForObject(
            """
            select count(*)
            from novels
            where id = ?
            """,
            Integer.class,
            id);
    return count != null && count > 0;
  }

  public void upsertRating(Long novelId, UUID userId, int score) {
    Instant now = Instant.now();
    int updated =
        jdbcTemplate.update(
            """
            update novel_ratings
            set score = ?, updated_at = ?
            where novel_id = ? and user_id = ?
            """,
            score,
            Timestamp.from(now),
            novelId,
            userId);
    if (updated > 0) {
      return;
    }

    try {
      jdbcTemplate.update(
          """
          insert into novel_ratings (novel_id, user_id, score, created_at, updated_at)
          values (?, ?, ?, ?, ?)
          """,
          novelId,
          userId,
          score,
          Timestamp.from(now),
          Timestamp.from(now));
    } catch (DuplicateKeyException ignored) {
      jdbcTemplate.update(
          """
          update novel_ratings
          set score = ?, updated_at = ?
          where novel_id = ? and user_id = ?
          """,
          score,
          Timestamp.from(now),
          novelId,
          userId);
    }
  }

  public void applyRatingDelta(Long novelId, int countDelta, int scoreDelta) {
    jdbcTemplate.update(
        """
        update novels
        set rating_count = rating_count + ?,
            rating_total = rating_total + ?,
            updated_at = ?
        where id = ?
        """,
        countDelta,
        scoreDelta,
        Timestamp.from(Instant.now()),
        novelId);
  }

  private NovelRecord mapRow(ResultSet rs, int rowNum) throws SQLException {
    return new NovelRecord(
        rs.getLong("id"),
        rs.getObject("user_id", UUID.class),
        rs.getString("title"),
        rs.getString("author"),
        rs.getString("excerpt"),
        rs.getString("content_object_key"),
        rs.getString("content_url"),
        rs.getLong("content_size"),
        rs.getString("content_sha256"),
        rs.getInt("rating_count"),
        rs.getBigDecimal("rating_total"),
        getNullableInteger(rs, "my_rating"),
        toInstant(rs.getTimestamp("created_at")),
        toInstant(rs.getTimestamp("updated_at")));
  }

  private Integer getNullableInteger(ResultSet rs, String column) throws SQLException {
    int value = rs.getInt(column);
    return rs.wasNull() ? null : value;
  }

  private double average(int ratingCount, BigDecimal ratingTotal) {
    if (ratingCount <= 0 || ratingTotal == null) {
      return 0;
    }
    return ratingTotal.doubleValue() / ratingCount;
  }

  private Instant toInstant(Timestamp timestamp) {
    return timestamp == null ? null : timestamp.toInstant();
  }
}
