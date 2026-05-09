package com.relay.backend.module.novel;

import com.relay.backend.common.error.AppException;
import com.relay.backend.common.error.ErrorCode;
import com.relay.backend.config.AppProperties;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.LocalDate;
import java.util.Base64;
import java.util.UUID;
import java.util.regex.Pattern;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

@Service
public class GithubNovelStorageService implements NovelStorageService {

  private static final Pattern CONTENT_PATTERN =
      Pattern.compile("\"content\"\\s*:\\s*\"([^\"]*)\"", Pattern.DOTALL);

  private final AppProperties.Github properties;
  private final HttpClient httpClient;

  public GithubNovelStorageService(AppProperties appProperties) {
    this.properties = appProperties.getNovelStorage().getGithub();
    this.httpClient = HttpClient.newHttpClient();
  }

  @Override
  public NovelStorageObject save(UUID userId, String title, String content) {
    RepositoryRef repository = repositoryRef();
    requireConfigured(repository);

    byte[] bytes = content.getBytes(StandardCharsets.UTF_8);
    String objectKey = objectKey(userId, title);
    String encodedContent = Base64.getEncoder().encodeToString(bytes);

    String body =
        """
        {"message":"%s","content":"%s","branch":"%s"}
        """
            .formatted(
                jsonEscape("Upload novel " + title),
                jsonEscape(encodedContent),
                jsonEscape(branch()))
            .trim();

    try {
      HttpRequest request =
          baseRequest(contentsUri(repository, objectKey, false))
              .header("Accept", "application/vnd.github+json")
              .header("Content-Type", "application/json")
              .PUT(HttpRequest.BodyPublishers.ofString(body))
              .build();
      HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
      if (response.statusCode() < 200 || response.statusCode() >= 300) {
        throw storageError("Unable to upload novel to GitHub: " + response.body());
      }
      return new NovelStorageObject(objectKey, rawUrl(repository, objectKey), bytes.length, sha256(bytes));
    } catch (AppException exception) {
      throw exception;
    } catch (Exception exception) {
      throw storageError("Unable to upload novel to GitHub: " + exception.getMessage());
    }
  }

  @Override
  public String read(String objectKey) {
    RepositoryRef repository = repositoryRef();
    requireConfigured(repository);
    try {
      HttpRequest request =
          baseRequest(contentsUri(repository, objectKey, true))
              .header("Accept", "application/vnd.github.raw")
              .GET()
              .build();
      HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
      if (response.statusCode() >= 200 && response.statusCode() < 300) {
        return response.body();
      }

      HttpRequest jsonRequest =
          baseRequest(contentsUri(repository, objectKey, true))
              .header("Accept", "application/vnd.github+json")
              .GET()
              .build();
      HttpResponse<String> jsonResponse =
          httpClient.send(jsonRequest, HttpResponse.BodyHandlers.ofString());
      if (jsonResponse.statusCode() < 200 || jsonResponse.statusCode() >= 300) {
        throw storageError("Unable to read novel from GitHub: " + jsonResponse.body());
      }
      String content = extractContent(jsonResponse.body());
      if (content.isBlank()) {
        throw storageError("GitHub returned empty novel content");
      }
      return new String(Base64.getMimeDecoder().decode(content), StandardCharsets.UTF_8);
    } catch (AppException exception) {
      throw exception;
    } catch (Exception exception) {
      throw storageError("Unable to read novel from GitHub: " + exception.getMessage());
    }
  }

  private HttpRequest.Builder baseRequest(URI uri) {
    return HttpRequest.newBuilder(uri)
        .header("Authorization", "Bearer " + token())
        .header("User-Agent", "relay-backend-local")
        .header("X-GitHub-Api-Version", "2022-11-28");
  }

  private URI contentsUri(RepositoryRef repository, String objectKey, boolean includeRef) {
    String path = encodePath(objectKey);
    String uri =
        "https://api.github.com/repos/"
            + repository.owner()
            + "/"
            + repository.repo()
            + "/contents/"
            + path;
    if (includeRef) {
      uri += "?ref=" + encode(branch());
    }
    return URI.create(uri);
  }

  private String objectKey(UUID userId, String title) {
    LocalDate now = LocalDate.now();
    String safeTitle =
        title == null || title.isBlank()
            ? "novel"
            : title.trim().replaceAll("[^A-Za-z0-9\\u4e00-\\u9fa5._-]+", "-");
    if (safeTitle.length() > 48) {
      safeTitle = safeTitle.substring(0, 48);
    }
    String basePath = trimSlashes(properties.getBasePath());
    return basePath
        + "/"
        + now.getYear()
        + "/"
        + "%02d".formatted(now.getMonthValue())
        + "/"
        + userId
        + "-"
        + UUID.randomUUID()
        + "-"
        + safeTitle
        + ".txt";
  }

  private String rawUrl(RepositoryRef repository, String objectKey) {
    return "https://raw.githubusercontent.com/"
        + repository.owner()
        + "/"
        + repository.repo()
        + "/"
        + branch()
        + "/"
        + encodePath(objectKey);
  }

  private RepositoryRef repositoryRef() {
    String value = properties.getRepository() == null ? "" : properties.getRepository().trim();
    if (value.startsWith("https://github.com/")) {
      value = value.substring("https://github.com/".length());
    } else if (value.startsWith("git@github.com:")) {
      value = value.substring("git@github.com:".length());
    }
    if (value.endsWith(".git")) {
      value = value.substring(0, value.length() - 4);
    }
    value = trimSlashes(value);
    String[] parts = value.split("/");
    if (parts.length != 2 || parts[0].isBlank() || parts[1].isBlank()) {
      return new RepositoryRef("", "");
    }
    return new RepositoryRef(parts[0], parts[1]);
  }

  private void requireConfigured(RepositoryRef repository) {
    if (repository.owner().isBlank() || repository.repo().isBlank() || token().isBlank()) {
      throw new AppException(
          ErrorCode.INTERNAL_ERROR,
          "GitHub novel storage is not configured",
          HttpStatus.INTERNAL_SERVER_ERROR);
    }
  }

  private String token() {
    return properties.getToken() == null ? "" : properties.getToken().trim();
  }

  private String branch() {
    String branch = properties.getBranch() == null ? "" : properties.getBranch().trim();
    return branch.isBlank() ? "main" : branch;
  }

  private String trimSlashes(String value) {
    if (value == null) {
      return "";
    }
    return value.replaceAll("^/+", "").replaceAll("/+$", "");
  }

  private String encodePath(String path) {
    return java.util.Arrays.stream(path.split("/"))
        .map(this::encode)
        .collect(java.util.stream.Collectors.joining("/"));
  }

  private String encode(String value) {
    return URLEncoder.encode(value, StandardCharsets.UTF_8).replace("+", "%20");
  }

  private String sha256(byte[] bytes) {
    try {
      MessageDigest digest = MessageDigest.getInstance("SHA-256");
      return Base64.getUrlEncoder().withoutPadding().encodeToString(digest.digest(bytes));
    } catch (Exception exception) {
      throw new IllegalStateException("Unable to hash novel content", exception);
    }
  }

  private AppException storageError(String message) {
    return new AppException(ErrorCode.INTERNAL_ERROR, message, HttpStatus.INTERNAL_SERVER_ERROR);
  }

  private String extractContent(String json) {
    if (json == null || json.isBlank()) {
      return "";
    }
    var matcher = CONTENT_PATTERN.matcher(json);
    if (!matcher.find()) {
      return "";
    }
    return matcher.group(1).replace("\\n", "\n").replace("\\r", "\r").replace("\\\"", "\"");
  }

  private String jsonEscape(String value) {
    if (value == null) {
      return "";
    }
    return value
        .replace("\\", "\\\\")
        .replace("\"", "\\\"")
        .replace("\r", "\\r")
        .replace("\n", "\\n");
  }

  private record RepositoryRef(String owner, String repo) {}
}
