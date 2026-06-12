package com.relay.backend.module.redeem;

import com.relay.backend.common.error.AppException;
import com.relay.backend.common.error.ErrorCode;
import com.relay.backend.module.redeem.dto.RedeemCodeResponse;
import com.relay.backend.module.user.BalanceUpdatePublisher;
import com.relay.backend.module.user.UserRepository;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RedeemCodeService {

  private final RedeemCodeRepository redeemCodeRepository;
  private final RedeemCodeRedisIndex redisIndex;
  private final UserRepository userRepository;
  private final BalanceUpdatePublisher balanceUpdatePublisher;
  private final Clock clock;

  @Autowired
  public RedeemCodeService(
      RedeemCodeRepository redeemCodeRepository,
      RedeemCodeRedisIndex redisIndex,
      UserRepository userRepository,
      BalanceUpdatePublisher balanceUpdatePublisher) {
    this(redeemCodeRepository, redisIndex, userRepository, balanceUpdatePublisher, Clock.systemUTC());
  }

  RedeemCodeService(
      RedeemCodeRepository redeemCodeRepository,
      RedeemCodeRedisIndex redisIndex,
      UserRepository userRepository,
      BalanceUpdatePublisher balanceUpdatePublisher,
      Clock clock) {
    this.redeemCodeRepository = redeemCodeRepository;
    this.redisIndex = redisIndex;
    this.userRepository = userRepository;
    this.balanceUpdatePublisher = balanceUpdatePublisher;
    this.clock = clock;
  }

  @Transactional
  public RedeemCodeResponse redeem(UUID userId, String code) {
    return redeem(userId, code, "");
  }

  @Transactional
  public RedeemCodeResponse redeem(UUID userId, String code, String redeemedIp) {
    String normalizedCode = normalizeCode(code);
    String normalizedIp = normalizeIp(redeemedIp);
    Instant now = clock.instant();
    RedeemCodeRecord codeRecord =
        redeemCodeRepository
            .findByCodeForUpdate(normalizedCode)
            .orElseThrow(
                () ->
                    new AppException(
                        ErrorCode.NOT_FOUND, "Redeem code does not exist", HttpStatus.NOT_FOUND));

    if (codeRecord.holderUserId() != null) {
      throw new AppException(ErrorCode.CONFLICT, "Redeem code has already been used", HttpStatus.CONFLICT);
    }
    if (!codeRecord.expiresAt().isAfter(now)) {
      throw new AppException(ErrorCode.VALIDATION_FAILED, "Redeem code has expired", HttpStatus.BAD_REQUEST);
    }
    if (redeemCodeRepository.hasUserRedeemedBatch(userId, codeRecord.batch())) {
      throw new AppException(ErrorCode.CONFLICT, "领取失败", HttpStatus.CONFLICT);
    }
    if (!normalizedIp.isBlank() && redeemCodeRepository.hasIpRedeemedBatch(normalizedIp, codeRecord.batch())) {
      throw new AppException(ErrorCode.CONFLICT, "领取失败", HttpStatus.CONFLICT);
    }

    String storedIp = normalizedIp.isBlank() ? null : normalizedIp;
    RedeemCodeRecord redeemed;
    try {
      redeemed = redeemCodeRepository.markRedeemed(codeRecord.id(), userId, storedIp, now);
    } catch (DataIntegrityViolationException | EmptyResultDataAccessException exception) {
      throw new AppException(ErrorCode.CONFLICT, "领取失败", HttpStatus.CONFLICT);
    }
    BigDecimal balance = userRepository.addBalance(userId, redeemed.amount());
    balanceUpdatePublisher.publish(userId, balance);
    redisIndex.add(redeemed);
    return new RedeemCodeResponse(redeemed.amount(), balance, redeemed.expiresAt());
  }

  @Transactional
  public boolean deductExpiredCode(Long codeId, Instant now) {
    RedeemCodeRecord codeRecord = redeemCodeRepository.findByIdForUpdate(codeId).orElse(null);
    if (codeRecord == null || codeRecord.expiredDeductedAt() != null) {
      return false;
    }
    if (codeRecord.holderUserId() == null || codeRecord.expiresAt().isAfter(now)) {
      return false;
    }

    BigDecimal balance = userRepository.addBalance(codeRecord.holderUserId(), codeRecord.amount().negate());
    balanceUpdatePublisher.publish(codeRecord.holderUserId(), balance);
    redeemCodeRepository.markExpiredDeducted(codeRecord.id(), now);
    return true;
  }

  public void rebuildExpirationIndex() {
    redisIndex.rebuild(redeemCodeRepository.findPendingExpirations());
  }

  private String normalizeCode(String code) {
    return code == null ? "" : code.trim();
  }

  private String normalizeIp(String ip) {
    return ip == null ? "" : ip.trim();
  }
}
