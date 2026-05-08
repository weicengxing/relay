package com.relay.backend.test;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;

@TestConfiguration
public class RedisTestConfig {

  @Bean
  @Primary
  public StringRedisTemplate stringRedisTemplate() {
    Map<String, String> values = new ConcurrentHashMap<>();
    StringRedisTemplate template = mock(StringRedisTemplate.class);
    @SuppressWarnings("unchecked")
    ValueOperations<String, String> ops = mock(ValueOperations.class);

    when(template.opsForValue()).thenReturn(ops);
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
    when(template.delete(anyString())).thenAnswer(invocation -> values.remove(invocation.getArgument(0)) != null);
    when(template.expire(anyString(), any(Duration.class))).thenReturn(true);
    return template;
  }
}
