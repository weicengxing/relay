package com.relay.backend.config;

import java.util.ArrayList;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public class AppProperties {

  private final Cors cors = new Cors();
  private final Ai ai = new Ai();
  private final Security security = new Security();
  private final Mail mail = new Mail();
  private final RateLimit rateLimit = new RateLimit();

  public Cors getCors() {
    return cors;
  }

  public Ai getAi() {
    return ai;
  }

  public Security getSecurity() {
    return security;
  }

  public Mail getMail() {
    return mail;
  }

  public RateLimit getRateLimit() {
    return rateLimit;
  }

  public static class Cors {
    private List<String> allowedOrigins = new ArrayList<>(List.of("http://localhost:5173"));

    public List<String> getAllowedOrigins() {
      return allowedOrigins;
    }

    public void setAllowedOrigins(List<String> allowedOrigins) {
      this.allowedOrigins = allowedOrigins;
    }
  }

  public static class Ai {
    private String apiBase = "https://api.openai.com/v1";

    public String getApiBase() {
      return apiBase;
    }

    public void setApiBase(String apiBase) {
      this.apiBase = apiBase;
    }
  }

  public static class Security {
    private String jwtSecret = "change-me-in-env";

    public String getJwtSecret() {
      return jwtSecret;
    }

    public void setJwtSecret(String jwtSecret) {
      this.jwtSecret = jwtSecret;
    }
  }

  public static class Mail {
    private String host = "smtp.qq.com";
    private int port = 465;
    private String username = "";
    private String password = "";

    public String getHost() {
      return host;
    }

    public void setHost(String host) {
      this.host = host;
    }

    public int getPort() {
      return port;
    }

    public void setPort(int port) {
      this.port = port;
    }

    public String getUsername() {
      return username;
    }

    public void setUsername(String username) {
      this.username = username;
    }

    public String getPassword() {
      return password;
    }

    public void setPassword(String password) {
      this.password = password;
    }
  }

  public static class RateLimit {
    private boolean enabled = true;
    private int windowSeconds = 60;
    private int maxRequests = 60;

    public boolean isEnabled() {
      return enabled;
    }

    public void setEnabled(boolean enabled) {
      this.enabled = enabled;
    }

    public int getWindowSeconds() {
      return windowSeconds;
    }

    public void setWindowSeconds(int windowSeconds) {
      this.windowSeconds = windowSeconds;
    }

    public int getMaxRequests() {
      return maxRequests;
    }

    public void setMaxRequests(int maxRequests) {
      this.maxRequests = maxRequests;
    }
  }
}
