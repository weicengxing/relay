package com.relay.backend.module.novel;

import com.relay.backend.common.error.AppException;
import com.relay.backend.common.error.ErrorCode;
import com.relay.backend.common.redis.RedisStateService;
import com.relay.backend.module.novel.dto.CreateNovelRequest;
import com.relay.backend.module.novel.dto.NovelResponse;
import com.relay.backend.module.novel.dto.NovelSummaryResponse;
import com.relay.backend.module.novel.dto.RateNovelRequest;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.data.redis.core.ZSetOperations;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class NovelService {

  private static final String LEADERBOARD_KEY = "novels:rating:leaderboard";

  private final NovelRepository novelRepository;
  private final RedisStateService redisStateService;
  private final NovelStorageService novelStorageService;

  public NovelService(
      NovelRepository novelRepository,
      RedisStateService redisStateService,
      NovelStorageService novelStorageService) {
    this.novelRepository = novelRepository;
    this.redisStateService = redisStateService;
    this.novelStorageService = novelStorageService;
  }

  @Transactional(readOnly = true)
  public List<NovelSummaryResponse> list(UUID viewerUserId) {
    return novelRepository.findAll(viewerUserId).stream().map(this::toSummary).toList();
  }

  @Transactional(readOnly = true)
  public NovelResponse detail(UUID viewerUserId, Long id) {
    return novelRepository
        .findById(id, viewerUserId)
        .map(this::toDetail)
        .orElseThrow(() -> new AppException(ErrorCode.NOT_FOUND, "Novel not found", HttpStatus.NOT_FOUND));
  }

  @Transactional
  public NovelResponse create(UUID userId, CreateNovelRequest request) {
    String title = request.title().trim();
    String author = request.author() == null ? "" : request.author().trim();
    String content = request.content().trim();
    String excerpt = excerpt(content);
    NovelStorageObject storageObject = novelStorageService.save(userId, title, content);
    NovelRecord record = novelRepository.create(userId, title, author, excerpt, storageObject);
    redisStateService.addSortedSetValue(LEADERBOARD_KEY, String.valueOf(record.id()), record.averageRating());
    return toDetail(record, content);
  }

  @Transactional
  public NovelResponse rate(UUID userId, Long id, RateNovelRequest request) {
    if (!novelRepository.exists(id)) {
      throw new AppException(ErrorCode.NOT_FOUND, "Novel not found", HttpStatus.NOT_FOUND);
    }

    int score = request.score();
    Integer previousScore = novelRepository.findRating(id, userId).orElse(null);
    novelRepository.upsertRating(id, userId, score);
    int countDelta = previousScore == null ? 1 : 0;
    int scoreDelta = previousScore == null ? score : score - previousScore;
    novelRepository.applyRatingDelta(id, countDelta, scoreDelta);

    NovelRecord updated = novelRepository.findById(id, userId).orElseThrow();
    redisStateService.addSortedSetValue(LEADERBOARD_KEY, String.valueOf(id), updated.averageRating());
    return toDetail(updated);
  }

  @Transactional(readOnly = true)
  public List<NovelSummaryResponse> ranking(UUID viewerUserId, int limit) {
    int normalizedLimit = Math.max(1, Math.min(limit, 50));
    var tuples =
        redisStateService.sortedSetReverseRangeWithScores(LEADERBOARD_KEY, 0, normalizedLimit);
    if (tuples == null || tuples.isEmpty()) {
      repopulateLeaderboard();
      tuples = redisStateService.sortedSetReverseRangeWithScores(LEADERBOARD_KEY, 0, normalizedLimit);
    }
    if (tuples == null || tuples.isEmpty()) {
      return novelRepository.findTopByRating(viewerUserId, normalizedLimit).stream()
          .map(this::toSummary)
          .toList();
    }

    List<Long> ids =
        tuples.stream()
            .map(ZSetOperations.TypedTuple::getValue)
            .filter(value -> value != null && value.matches("\\d+"))
            .map(Long::valueOf)
            .toList();
    Map<Long, Integer> rank =
        ids.stream().collect(java.util.stream.Collectors.toMap(id -> id, ids::indexOf));
    return novelRepository.findByIds(ids, viewerUserId).stream()
        .sorted(Comparator.comparingInt(record -> rank.getOrDefault(record.id(), Integer.MAX_VALUE)))
        .map(this::toSummary)
        .toList();
  }

  private void repopulateLeaderboard() {
    redisStateService.replaceSortedSet(LEADERBOARD_KEY, novelRepository.findLeaderboardScores());
  }

  private NovelSummaryResponse toSummary(NovelRecord record) {
    return new NovelSummaryResponse(
        record.id(),
        record.title(),
        record.author(),
        record.excerpt(),
        round(record.averageRating()),
        record.ratingCount(),
        record.myRating(),
        record.createdAt());
  }

  private NovelResponse toDetail(NovelRecord record) {
    return toDetail(record, novelStorageService.read(record.contentObjectKey()));
  }

  private NovelResponse toDetail(NovelRecord record, String content) {
    return new NovelResponse(
        record.id(),
        record.title(),
        record.author(),
        content,
        record.contentUrl(),
        round(record.averageRating()),
        record.ratingCount(),
        record.myRating(),
        record.createdAt(),
        record.updatedAt());
  }

  private String excerpt(String content) {
    if (content == null || content.isBlank()) {
      return "";
    }
    String compact = content.replaceAll("\\s+", " ").trim();
    return compact.length() <= 140 ? compact : compact.substring(0, 140) + "...";
  }

  private double round(double value) {
    return Math.round(value * 10.0) / 10.0;
  }
}
