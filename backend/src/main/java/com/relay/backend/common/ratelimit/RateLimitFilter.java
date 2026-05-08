package com.relay.backend.common.ratelimit;

import com.relay.backend.common.error.ErrorCode;
import com.relay.backend.common.redis.RedisStateService;
import com.relay.backend.common.web.ClientIpResolver;
import com.relay.backend.config.AppProperties;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.time.Duration;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class RateLimitFilter extends OncePerRequestFilter {

  private final AppProperties appProperties;
  private final ClientIpResolver clientIpResolver;
  private final RedisStateService redisStateService;

  @Autowired
  RateLimitFilter(
      AppProperties appProperties,
      ClientIpResolver clientIpResolver,
      RedisStateService redisStateService) {
    this.appProperties = appProperties;
    this.clientIpResolver = clientIpResolver;
    this.redisStateService = redisStateService;
  }

  @Override
  protected boolean shouldNotFilter(HttpServletRequest request) {
    return !appProperties.getRateLimit().isEnabled() || !request.getRequestURI().startsWith("/api/");
  }

  @Override
  protected void doFilterInternal(
      HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
      throws ServletException, IOException {
    String key = clientIpResolver.resolve(request);

    if (isLimited(key)) {
      response.setStatus(HttpStatus.TOO_MANY_REQUESTS.value());
      response.setContentType(MediaType.APPLICATION_JSON_VALUE);
      response
          .getWriter()
          .write(
              """
              {"success":false,"data":null,"error":{"code":"%s","message":"Too many requests","details":{}}}
              """
                  .formatted(ErrorCode.RATE_LIMITED)
                  .trim());
      return;
    }

    filterChain.doFilter(request, response);
  }

  private boolean isLimited(String key) {
    int windowSeconds = appProperties.getRateLimit().getWindowSeconds();
    int maxRequests = appProperties.getRateLimit().getMaxRequests();
    long window = System.currentTimeMillis() / (windowSeconds * 1000L);
    long count =
        redisStateService.increment(
            "relay:rate:ip:" + key + ":" + window, Duration.ofSeconds(windowSeconds + 5L));
    return count > maxRequests;
  }
}
