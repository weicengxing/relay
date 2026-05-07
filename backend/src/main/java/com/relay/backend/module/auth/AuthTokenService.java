package com.relay.backend.module.auth;

import com.relay.backend.config.AppProperties;
import com.relay.backend.module.user.UserAccount;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

@Component
public class AuthTokenService {

  private static final String HMAC_ALGORITHM = "HmacSHA256";
  private static final Base64.Encoder BASE64_URL = Base64.getUrlEncoder().withoutPadding();

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
        {"sub":"%s","email":"%s","iat":%d,"exp":%d}
        """
            .formatted(user.id(), user.email(), now.getEpochSecond(), now.plusSeconds(86400).getEpochSecond())
            .trim();

    String unsigned = encode(header) + "." + encode(payload);
    return unsigned + "." + sign(unsigned);
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
}
