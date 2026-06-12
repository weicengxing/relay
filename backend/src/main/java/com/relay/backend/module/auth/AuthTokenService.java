package com.relay.backend.module.auth;

import com.relay.backend.common.error.AppException;
import com.relay.backend.common.error.ErrorCode;
import com.relay.backend.config.AppProperties;
import com.relay.backend.module.user.UserAccount;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Instant;
import java.util.Base64;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

@Component
public class AuthTokenService {

  private static final String HMAC_ALGORITHM = "HmacSHA256";
  private static final Base64.Encoder BASE64_URL = Base64.getUrlEncoder().withoutPadding();
  private static final Base64.Decoder BASE64_URL_DECODER = Base64.getUrlDecoder();
  private static final Pattern SUB_PATTERN = Pattern.compile("\"sub\"\\s*:\\s*\"([^\"]+)\"");

  private final AppProperties appProperties;
  private final Clock clock;

  @Autowired
  public AuthTokenService(AppProperties appProperties) {
    this(appProperties, Clock.systemUTC());
  }

  AuthTokenService(AppProperties appProperties, Clock clock) {
    this.appProperties = appProperties;
    this.clock = clock;
  }

  public String issue(UserAccount user) {
    Instant now = clock.instant();
    String header = "{\"alg\":\"HS256\",\"typ\":\"JWT\"}";
    String payload =
        """
        {"sub":"%s","email":"%s","iat":%d}
        """
            .formatted(user.id(), user.email(), now.getEpochSecond())
            .trim();

    String unsigned = encode(header) + "." + encode(payload);
    return unsigned + "." + sign(unsigned);
  }

  public UUID verifyAndGetUserId(String token) {
    String[] parts = token == null ? new String[0] : token.split("\\.");
    if (parts.length != 3) {
      throw unauthorized();
    }

    String unsigned = parts[0] + "." + parts[1];
    if (!MessageDigest.isEqual(sign(unsigned).getBytes(StandardCharsets.UTF_8), parts[2].getBytes(StandardCharsets.UTF_8))) {
      throw unauthorized();
    }

    String payload = new String(BASE64_URL_DECODER.decode(parts[1]), StandardCharsets.UTF_8);
    Matcher subMatcher = SUB_PATTERN.matcher(payload);
    if (!subMatcher.find()) {
      throw unauthorized();
    }

    return UUID.fromString(subMatcher.group(1));
  }

  private String encode(String value) {
    return BASE64_URL.encodeToString(value.getBytes(StandardCharsets.UTF_8));
  }

  private String sign(String value) {
    try {
      Mac mac = Mac.getInstance(HMAC_ALGORITHM);
      mac.init(
          new SecretKeySpec(
              appProperties.getSecurity().getJwtSecret().getBytes(StandardCharsets.UTF_8),
              HMAC_ALGORITHM));
      return BASE64_URL.encodeToString(mac.doFinal(value.getBytes(StandardCharsets.UTF_8)));
    } catch (Exception exception) {
      throw new IllegalStateException("Unable to sign auth token", exception);
    }
  }

  private AppException unauthorized() {
    return new AppException(ErrorCode.UNAUTHORIZED, "Unauthorized", HttpStatus.UNAUTHORIZED);
  }
}
