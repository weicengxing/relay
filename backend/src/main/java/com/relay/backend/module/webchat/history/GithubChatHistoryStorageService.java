package com.relay.backend.module.webchat.history;

import com.relay.backend.common.error.AppException;
import com.relay.backend.common.error.ErrorCode;
import com.relay.backend.config.AppProperties;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

@Service
public class GithubChatHistoryStorageService {

  private final AppProperties.Github properties;
  private final ObjectMapper objectMapper;
  private final HttpClient httpClient;

  public GithubChatHistoryStorageService(AppProperties appProperties, ObjectMapper objectMapper) {
    this.properties = appProperties.getChatHistory().getGithub();
    this.objectMapper = objectMapper;
    this.httpClient = HttpClient.newHttpClient();
  }

  public boolean isConfigured() {
    RepositoryRef repository = repositoryRef();
    return !repository.owner().isBlank() && !repository.repo().isBlank() && !token().isBlank();
  }

  public Optional<StoredFile> read(String objectKey) {
    RepositoryRef repository = repositoryRef();
    requireConfigured(repository);
    try {
      HttpRequest request =
          baseRequest(contentsUri(repository, objectKey, true))
              .header("Accept", "application/vnd.github+json")
              .GET()
              .build();
      HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
      if (response.statusCode() == 404) {
        return Optional.empty();
      }
      if (response.statusCode() < 200 || response.statusCode() >= 300) {
        throw storageError("Unable to read chat history from GitHub: " + response.body());
      }
      JsonNode root = objectMapper.readTree(response.body());
      String encoded = textAt(root, "content");
      String sha = textAt(root, "sha");
      if (encoded == null || encoded.isBlank()) {
        return Optional.of(new StoredFile("", sha, 0));
      }
      byte[] bytes = Base64.getMimeDecoder().decode(encoded);
      return Optional.of(new StoredFile(new String(bytes, StandardCharsets.UTF_8), sha, bytes.length));
    } catch (AppException exception) {
      throw exception;
    } catch (Exception exception) {
      throw storageError("Unable to read chat history from GitHub: " + exception.getMessage());
    }
  }

  public StoredWrite write(String objectKey, String content, String sha, String message) {
    RepositoryRef repository = repositoryRef();
    requireConfigured(repository);
    byte[] bytes = content.getBytes(StandardCharsets.UTF_8);
    Map<String, Object> body = new LinkedHashMap<>();
    body.put("message", message);
    body.put("content", Base64.getEncoder().encodeToString(bytes));
    body.put("branch", branch());
    if (sha != null && !sha.isBlank()) {
      body.put("sha", sha);
    }

    try {
      HttpRequest request =
          baseRequest(contentsUri(repository, objectKey, false))
              .header("Accept", "application/vnd.github+json")
              .header("Content-Type", "application/json")
              .PUT(HttpRequest.BodyPublishers.ofString(objectMapper.writeValueAsString(body), StandardCharsets.UTF_8))
              .build();
      HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
      if (response.statusCode() < 200 || response.statusCode() >= 300) {
        throw storageError("Unable to write chat history to GitHub: " + response.body());
      }
      return new StoredWrite(rawUrl(repository, objectKey), bytes.length);
    } catch (AppException exception) {
      throw exception;
    } catch (Exception exception) {
      throw storageError("Unable to write chat history to GitHub: " + exception.getMessage());
    }
  }

  public String objectKey(java.util.UUID userId, int sequence) {
    String basePath = trimSlashes(properties.getBasePath());
    String fileName = userId + "-" + "%06d".formatted(sequence) + ".jsonl";
    return (basePath.isBlank() ? "" : basePath + "/") + userId + "/" + fileName;
  }

  private HttpRequest.Builder baseRequest(URI uri) {
    return HttpRequest.newBuilder(uri)
        .header("Authorization", "Bearer " + token())
        .header("User-Agent", "relay-backend-local")
        .header("X-GitHub-Api-Version", "2022-11-28");
  }

  private URI contentsUri(RepositoryRef repository, String objectKey, boolean includeRef) {
    String uri =
        "https://api.github.com/repos/"
            + repository.owner()
            + "/"
            + repository.repo()
            + "/contents/"
            + encodePath(objectKey);
    if (includeRef) {
      uri += "?ref=" + encode(branch());
    }
    return URI.create(uri);
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
          "GitHub chat history storage is not configured",
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

  private String textAt(JsonNode node, String field) {
    if (node == null || node.isNull()) {
      return null;
    }
    JsonNode child = node.get(field);
    if (child == null || child.isNull() || !child.isTextual()) {
      return null;
    }
    String value = child.asText();
    return value == null || value.isBlank() ? null : value;
  }

  private AppException storageError(String message) {
    return new AppException(ErrorCode.INTERNAL_ERROR, message, HttpStatus.INTERNAL_SERVER_ERROR);
  }

  public record StoredFile(String content, String sha, long sizeBytes) {}

  public record StoredWrite(String url, long sizeBytes) {}

  private record RepositoryRef(String owner, String repo) {}
}
