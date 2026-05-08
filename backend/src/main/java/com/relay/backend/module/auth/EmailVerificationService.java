package com.relay.backend.module.auth;

import com.relay.backend.common.error.AppException;
import com.relay.backend.common.error.ErrorCode;
import com.relay.backend.common.redis.RedisStateService;
import com.relay.backend.config.AppProperties;
import com.relay.backend.module.auth.dto.RegisterCodeResponse;
import java.security.SecureRandom;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

@Service
public class EmailVerificationService {

  private final AppProperties appProperties;
  private final VerificationMailSender mailSender;
  private final RedisStateService redisStateService;
  private final SecureRandom secureRandom = new SecureRandom();

  @Autowired
  EmailVerificationService(
      AppProperties appProperties, VerificationMailSender mailSender, RedisStateService redisStateService) {
    this.appProperties = appProperties;
    this.mailSender = mailSender;
    this.redisStateService = redisStateService;
  }

  public RegisterCodeResponse sendRegisterCode(String email) {
    String normalizedEmail = normalize(email);
    int ttlMinutes = appProperties.getVerification().getCodeTtlMinutes();
    String code = "%06d".formatted(secureRandom.nextInt(1_000_000));
    redisStateService.set(registerCodeKey(normalizedEmail), code, Duration.ofMinutes(ttlMinutes));
    mailSender.sendRegisterCode(normalizedEmail, code, ttlMinutes);
    return new RegisterCodeResponse(normalizedEmail, ttlMinutes);
  }

  public void verifyRegisterCode(String email, String code) {
    String normalizedEmail = normalize(email);
    String stored = redisStateService.get(registerCodeKey(normalizedEmail));

    if (stored == null || !stored.equals(code)) {
      throw new AppException(
          ErrorCode.INVALID_VERIFICATION_CODE,
          "Invalid or expired verification code",
          HttpStatus.BAD_REQUEST);
    }

    redisStateService.delete(registerCodeKey(normalizedEmail));
  }

  public void putRegisterCodeForTest(String email, String code) {
    redisStateService.set(registerCodeKey(normalize(email)), code, Duration.ofMinutes(10));
  }

  private String normalize(String email) {
    return email.trim().toLowerCase();
  }

  private String registerCodeKey(String email) {
    return "relay:verify:register:" + email;
  }
}
