package com.relay.backend.module.redeem;

import java.time.Clock;
import java.time.Instant;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.data.redis.core.ZSetOperations;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class RedeemCodeExpirationWorker implements ApplicationRunner {

  private static final Logger log = LoggerFactory.getLogger(RedeemCodeExpirationWorker.class);
  private static final int BATCH_SIZE = 100;

  private final RedeemCodeService redeemCodeService;
  private final RedeemCodeRedisIndex redisIndex;
  private final Clock clock;

  @Autowired
  public RedeemCodeExpirationWorker(
      RedeemCodeService redeemCodeService, RedeemCodeRedisIndex redisIndex) {
    this(redeemCodeService, redisIndex, Clock.systemUTC());
  }

  RedeemCodeExpirationWorker(
      RedeemCodeService redeemCodeService, RedeemCodeRedisIndex redisIndex, Clock clock) {
    this.redeemCodeService = redeemCodeService;
    this.redisIndex = redisIndex;
    this.clock = clock;
  }

  @Override
  public void run(ApplicationArguments args) {
    try {
      redeemCodeService.rebuildExpirationIndex();
    } catch (Exception exception) {
      log.warn("Unable to rebuild redeem code expiration index", exception);
    }
  }

  @Scheduled(fixedDelayString = "${relay.redeem.expiration-scan-delay-ms:30000}")
  public void deductExpiredCodes() {
    Instant now = clock.instant();
    Set<ZSetOperations.TypedTuple<String>> dueCodes = redisIndex.due(now, BATCH_SIZE);
    if (dueCodes == null || dueCodes.isEmpty()) {
      return;
    }

    for (ZSetOperations.TypedTuple<String> dueCode : dueCodes) {
      String value = dueCode.getValue();
      Long codeId = parseId(value);
      if (codeId == null) {
        if (value != null) {
          redisIndex.removeByValue(value);
        }
        continue;
      }
      try {
        redeemCodeService.deductExpiredCode(codeId, now);
        redisIndex.remove(codeId);
      } catch (Exception exception) {
        log.warn("Unable to deduct expired redeem code id={}", codeId, exception);
      }
    }
  }

  private Long parseId(String value) {
    if (value == null || value.isBlank()) {
      return null;
    }
    try {
      return Long.parseLong(value);
    } catch (NumberFormatException exception) {
      return null;
    }
  }
}
