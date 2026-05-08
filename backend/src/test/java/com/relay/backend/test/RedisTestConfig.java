package com.relay.backend.test;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.data.redis.core.DefaultTypedTuple;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.data.redis.core.ZSetOperations;

@TestConfiguration
public class RedisTestConfig {

  @Bean
  @Primary
  public StringRedisTemplate stringRedisTemplate() {
    Map<String, String> values = new ConcurrentHashMap<>();
    Map<String, Map<String, Double>> sortedSets = new ConcurrentHashMap<>();
    StringRedisTemplate template = mock(StringRedisTemplate.class);
    @SuppressWarnings("unchecked")
    ValueOperations<String, String> ops = mock(ValueOperations.class);
    @SuppressWarnings("unchecked")
    ZSetOperations<String, String> zSetOps = mock(ZSetOperations.class);

    when(template.opsForValue()).thenReturn(ops);
    when(template.opsForZSet()).thenReturn(zSetOps);
    when(ops.get(anyString())).thenAnswer(invocation -> values.get(invocation.getArgument(0)));
    doAnswer(
            invocation -> {
              values.put(invocation.getArgument(0), invocation.getArgument(1));
              return null;
            })
        .when(ops)
        .set(anyString(), anyString(), any(Duration.class));
    when(ops.increment(anyString()))
        .thenAnswer(
            invocation -> {
              String key = invocation.getArgument(0);
              long next = Long.parseLong(values.getOrDefault(key, "0")) + 1;
              values.put(key, String.valueOf(next));
              return next;
            });
    when(ops.increment(anyString(), anyLong()))
        .thenAnswer(
            invocation -> {
              String key = invocation.getArgument(0);
              long delta = invocation.getArgument(1);
              long next = Long.parseLong(values.getOrDefault(key, "0")) + delta;
              values.put(key, String.valueOf(next));
              return next;
            });
    when(ops.decrement(anyString()))
        .thenAnswer(
            invocation -> {
              String key = invocation.getArgument(0);
              long next = Long.parseLong(values.getOrDefault(key, "0")) - 1;
              values.put(key, String.valueOf(next));
              return next;
            });
    when(zSetOps.add(anyString(), anyString(), org.mockito.ArgumentMatchers.anyDouble()))
        .thenAnswer(
            invocation -> {
              String key = invocation.getArgument(0);
              String value = invocation.getArgument(1);
              Double score = invocation.getArgument(2);
              sortedSets.computeIfAbsent(key, ignored -> new ConcurrentHashMap<>()).put(value, score);
              return true;
            });
    when(zSetOps.remove(anyString(), anyString()))
        .thenAnswer(
            invocation -> {
              String key = invocation.getArgument(0);
              String value = invocation.getArgument(1);
              Map<String, Double> set = sortedSets.getOrDefault(key, new HashMap<>());
              return set.remove(value) == null ? 0L : 1L;
            });
    when(zSetOps.rangeByScoreWithScores(
            anyString(),
            org.mockito.ArgumentMatchers.anyDouble(),
            org.mockito.ArgumentMatchers.anyDouble(),
            anyLong(),
            anyLong()))
        .thenAnswer(
            invocation -> {
              String key = invocation.getArgument(0);
              Double min = invocation.getArgument(1);
              Double max = invocation.getArgument(2);
              Long offset = invocation.getArgument(3);
              Long count = invocation.getArgument(4);
              return sortedSets.getOrDefault(key, Map.of()).entrySet().stream()
                  .filter(entry -> entry.getValue() >= min && entry.getValue() <= max)
                  .sorted(Map.Entry.comparingByValue())
                  .skip(offset)
                  .limit(count)
                  .map(entry -> new DefaultTypedTuple<>(entry.getKey(), entry.getValue()))
                  .collect(Collectors.toCollection(java.util.LinkedHashSet::new));
            });
    when(template.delete(anyString()))
        .thenAnswer(
            invocation -> {
              String key = invocation.getArgument(0);
              boolean removedValue = values.remove(key) != null;
              boolean removedSet = sortedSets.remove(key) != null;
              return removedValue || removedSet;
            });
    when(template.expire(anyString(), any(Duration.class))).thenReturn(true);
    return template;
  }
}
