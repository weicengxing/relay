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
  private final Verification verification = new Verification();
  private final NovelStorage novelStorage = new NovelStorage();

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

  public Verification getVerification() {
    return verification;
  }

  public NovelStorage getNovelStorage() {
    return novelStorage;
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
    private String from = "";

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

    public String getFrom() {
      return from;
    }

    public void setFrom(String from) {
      this.from = from;
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

  public static class Verification {
    private int codeTtlMinutes = 10;

    public int getCodeTtlMinutes() {
      return codeTtlMinutes;
    }

    public void setCodeTtlMinutes(int codeTtlMinutes) {
      this.codeTtlMinutes = codeTtlMinutes;
    }
  }

  public static class NovelStorage {
    private final Github github = new Github();

    public Github getGithub() {
      return github;
    }
  }

  public static class Github {
    private String repository = "";
    private String branch = "main";
    private String basePath = "novels";
    private String token = "";

    public String getRepository() {
      return repository;
    }

    public void setRepository(String repository) {
      this.repository = repository;
    }

    public String getBranch() {
      return branch;
    }

    public void setBranch(String branch) {
      this.branch = branch;
    }

    public String getBasePath() {
      return basePath;
    }

    public void setBasePath(String basePath) {
      this.basePath = basePath;
    }

    public String getToken() {
      return token;
    }

    public void setToken(String token) {
      this.token = token;
    }
  }
}
