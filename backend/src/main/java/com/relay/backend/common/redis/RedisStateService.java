package com.relay.backend.common.redis;

import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisStateService {

  private final StringRedisTemplate redisTemplate;

  public RedisStateService(StringRedisTemplate redisTemplate) {
    this.redisTemplate = redisTemplate;
  }

  public void set(String key, String value, Duration ttl) {
    redisTemplate.opsForValue().set(key, value, ttl);
  }

  public String get(String key) {
    return redisTemplate.opsForValue().get(key);
  }

  public void delete(String key) {
    redisTemplate.delete(key);
  }

  public long increment(String key, Duration ttl) {
    Long count = redisTemplate.opsForValue().increment(key);
    if (count != null && count == 1) {
      redisTemplate.expire(key, ttl);
    }
    return count == null ? 0 : count;
  }

  public long incrementBy(String key, long delta, Duration ttl) {
    Long count = redisTemplate.opsForValue().increment(key, delta);
    if (count != null && count == delta) {
      redisTemplate.expire(key, ttl);
    }
    return count == null ? 0 : count;
  }

  public void decrement(String key) {
    redisTemplate.opsForValue().decrement(key);
  }
}
