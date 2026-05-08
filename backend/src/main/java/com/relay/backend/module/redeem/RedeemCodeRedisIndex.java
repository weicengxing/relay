package com.relay.backend.module.redeem;

import com.relay.backend.common.redis.RedisStateService;
import java.time.Instant;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.data.redis.core.ZSetOperations;
import org.springframework.stereotype.Component;

@Component
public class RedeemCodeRedisIndex {

  static final String EXPIRING_CODES_KEY = "relay:redeem-codes:expiring";

  private final RedisStateService redisStateService;

  public RedeemCodeRedisIndex(RedisStateService redisStateService) {
    this.redisStateService = redisStateService;
  }

  public void rebuild(Iterable<RedeemCodeRecord> records) {
    Map<String, Double> values =
        java.util.stream.StreamSupport.stream(records.spliterator(), false)
            .collect(Collectors.toMap(record -> String.valueOf(record.id()), this::score, (first, ignored) -> first));
    redisStateService.replaceSortedSet(EXPIRING_CODES_KEY, values);
  }

  public void add(RedeemCodeRecord record) {
    redisStateService.addSortedSetValue(EXPIRING_CODES_KEY, String.valueOf(record.id()), score(record));
  }

  public void remove(Long id) {
    redisStateService.removeSortedSetValue(EXPIRING_CODES_KEY, String.valueOf(id));
  }

  public void removeByValue(String value) {
    redisStateService.removeSortedSetValue(EXPIRING_CODES_KEY, value);
  }

  public Set<ZSetOperations.TypedTuple<String>> due(Instant now, long limit) {
    return redisStateService.sortedSetRangeByScoreWithScores(
        EXPIRING_CODES_KEY, Double.NEGATIVE_INFINITY, now.toEpochMilli(), limit);
  }

  private double score(RedeemCodeRecord record) {
    return record.expiresAt().toEpochMilli();
  }
}
