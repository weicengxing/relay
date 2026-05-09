package com.relay.backend.module.webchat.history;

import com.relay.backend.common.error.AppException;
import com.relay.backend.common.error.ErrorCode;
import com.relay.backend.config.AppProperties;
import com.relay.backend.module.webchat.dto.WebChatMessageRequest;
import com.relay.backend.module.webchat.dto.WebChatMessageResponse;
import com.relay.backend.module.webchat.history.GithubChatHistoryStorageService.StoredFile;
import com.relay.backend.module.webchat.history.GithubChatHistoryStorageService.StoredWrite;
import com.relay.backend.module.webchat.history.dto.ChatHistoryDetailResponse;
import com.relay.backend.module.webchat.history.dto.ChatHistoryFileResponse;
import com.relay.backend.module.webchat.history.dto.ChatHistoryImageResponse;
import com.relay.backend.module.webchat.history.dto.ChatHistoryPageResponse;
import com.relay.backend.module.webchat.history.dto.ChatHistoryTurnResponse;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

@Service
public class ChatHistoryService {

  private static final Logger log = LoggerFactory.getLogger(ChatHistoryService.class);

  private final ChatHistoryRepository repository;
  private final GithubChatHistoryStorageService storageService;
  private final AppProperties appProperties;
  private final ObjectMapper objectMapper;
  private final Map<UUID, Object> userLocks = new ConcurrentHashMap<>();

  public ChatHistoryService(
      ChatHistoryRepository repository,
      GithubChatHistoryStorageService storageService,
      AppProperties appProperties,
      ObjectMapper objectMapper) {
    this.repository = repository;
    this.storageService = storageService;
    this.appProperties = appProperties;
    this.objectMapper = objectMapper;
  }

  @Async
  public void recordTurnAsync(
      UUID userId, WebChatMessageRequest request, WebChatMessageResponse response) {
    if (!appProperties.getChatHistory().isEnabled()) {
      return;
    }
    if (!storageService.isConfigured()) {
      log.warn("GitHub chat history storage is not configured; skipping chat history record");
      return;
    }

    try {
      synchronized (userLocks.computeIfAbsent(userId, ignored -> new Object())) {
        appendTurn(userId, request, response);
      }
    } catch (Exception exception) {
      log.error("Unable to record web chat history for user {}", userId, exception);
    }
  }

  public ChatHistoryPageResponse list(UUID userId, int page, int size) {
    int normalizedPage = Math.max(page, 1);
    int normalizedSize = Math.min(Math.max(size, 1), 50);
    int offset = (normalizedPage - 1) * normalizedSize;
    int total = repository.count(userId);
    List<ChatHistoryFileResponse> items =
        repository.findPage(userId, normalizedSize, offset).stream().map(this::toFileResponse).toList();
    return new ChatHistoryPageResponse(
        items,
        normalizedPage,
        normalizedSize,
        total,
        offset + items.size() < total);
  }

  public ChatHistoryDetailResponse detail(UUID userId, Long id) {
    ChatHistoryFile file =
        repository
            .findById(userId, id)
            .orElseThrow(() -> new AppException(ErrorCode.NOT_FOUND, "Chat history not found", HttpStatus.NOT_FOUND));
    String content = storageService.read(file.objectKey()).map(StoredFile::content).orElse("");
    return new ChatHistoryDetailResponse(toFileResponse(file), parseTurns(content));
  }

  private void appendTurn(UUID userId, WebChatMessageRequest request, WebChatMessageResponse response)
      throws Exception {
    String line = objectMapper.writeValueAsString(turnDocument(userId, request, response)) + "\n";
    long lineBytes = line.getBytes(StandardCharsets.UTF_8).length;
    long maxFileBytes = Math.max(128 * 1024, appProperties.getChatHistory().getMaxFileBytes());

    ChatHistoryFile target = repository.findLatest(userId).orElse(null);
    if (target == null || (target.sizeBytes() > 0 && target.sizeBytes() + lineBytes > maxFileBytes)) {
      int sequence = target == null ? 1 : target.sequence() + 1;
      target = repository.create(userId, sequence, storageService.objectKey(userId, sequence));
    }

    Optional<StoredFile> stored = storageService.read(target.objectKey());
    String currentContent = stored.map(StoredFile::content).orElse("");
    String sha = stored.map(StoredFile::sha).orElse(null);
    if (!currentContent.isEmpty()
        && currentContent.getBytes(StandardCharsets.UTF_8).length + lineBytes > maxFileBytes) {
      int sequence = target.sequence() + 1;
      target = repository.create(userId, sequence, storageService.objectKey(userId, sequence));
      currentContent = "";
      sha = null;
    }

    String nextContent = currentContent + line;
    StoredWrite written =
        storageService.write(target.objectKey(), nextContent, sha, "Append web chat history " + userId);
    repository.updateAfterWrite(target.id(), written.url(), written.sizeBytes(), target.turnCount() + 1);
  }

  private Map<String, Object> turnDocument(
      UUID userId, WebChatMessageRequest request, WebChatMessageResponse response) {
    Map<String, Object> document = new LinkedHashMap<>();
    document.put("id", UUID.randomUUID().toString());
    document.put("created_at", Instant.now().toString());
    document.put("user_id", userId.toString());
    document.put("conversation_id", response.conversationId());
    document.put("parent_message_id", response.parentMessageId());
    document.put("model", response.model());
    document.put("config_id", response.configId());
    document.put("config_name", response.configName());

    Map<String, Object> user = new LinkedHashMap<>();
    user.put("message", request.message() == null ? "" : request.message());
    user.put("images", imageDocuments(request.images()));
    document.put("user", user);

    Map<String, Object> assistant = new LinkedHashMap<>();
    assistant.put("answer", response.answer() == null ? "" : response.answer());
    document.put("assistant", assistant);
    return document;
  }

  private List<Map<String, Object>> imageDocuments(
      List<WebChatMessageRequest.ImageAttachment> images) {
    if (images == null || images.isEmpty()) {
      return List.of();
    }
    List<Map<String, Object>> result = new ArrayList<>();
    for (WebChatMessageRequest.ImageAttachment image : images) {
      if (image == null) {
        continue;
      }
      Map<String, Object> item = new LinkedHashMap<>();
      item.put("name", image.name());
      item.put("media_type", image.mediaType());
      item.put("size", image.size());
      item.put("width", image.width());
      item.put("height", image.height());
      item.put("data", image.data());
      result.add(item);
    }
    return result;
  }

  private List<ChatHistoryTurnResponse> parseTurns(String content) {
    if (content == null || content.isBlank()) {
      return List.of();
    }
    List<ChatHistoryTurnResponse> turns = new ArrayList<>();
    for (String line : content.split("\\R")) {
      if (line.isBlank()) {
        continue;
      }
      try {
        turns.add(toTurnResponse(objectMapper.readTree(line)));
      } catch (Exception ignored) {
        // Keep reading the rest of the file if one JSONL row is malformed.
      }
    }
    Collections.reverse(turns);
    return turns;
  }

  private ChatHistoryTurnResponse toTurnResponse(JsonNode node) {
    JsonNode user = node.path("user");
    JsonNode assistant = node.path("assistant");
    return new ChatHistoryTurnResponse(
        instantAt(node, "created_at"),
        textAt(node, "conversation_id"),
        textAt(node, "parent_message_id"),
        textAt(node, "model"),
        textAt(node, "config_name"),
        textAt(user, "message"),
        imageResponses(user.path("images")),
        textAt(assistant, "answer"));
  }

  private List<ChatHistoryImageResponse> imageResponses(JsonNode images) {
    if (images == null || !images.isArray()) {
      return List.of();
    }
    List<ChatHistoryImageResponse> result = new ArrayList<>();
    for (JsonNode image : images) {
      result.add(
          new ChatHistoryImageResponse(
              textAt(image, "name"),
              textAt(image, "media_type"),
              longAt(image, "size"),
              intAt(image, "width"),
              intAt(image, "height"),
              textAt(image, "data")));
    }
    return result;
  }

  private ChatHistoryFileResponse toFileResponse(ChatHistoryFile file) {
    return new ChatHistoryFileResponse(
        file.id(),
        file.sequence(),
        file.objectKey(),
        file.contentUrl(),
        file.sizeBytes(),
        file.turnCount(),
        file.createdAt(),
        file.updatedAt());
  }

  private Instant instantAt(JsonNode node, String field) {
    String value = textAt(node, field);
    if (value == null) {
      return null;
    }
    try {
      return Instant.parse(value);
    } catch (Exception exception) {
      return null;
    }
  }

  private String textAt(JsonNode node, String field) {
    if (node == null || node.isNull()) {
      return null;
    }
    JsonNode child = node.get(field);
    if (child == null
        || child.isNull()
        || (!child.isTextual() && !child.isNumber() && !child.isBoolean())) {
      return null;
    }
    String value = child.asText();
    return value == null ? null : value;
  }

  private Long longAt(JsonNode node, String field) {
    JsonNode child = node == null ? null : node.get(field);
    return child != null && child.isNumber() ? child.asLong() : null;
  }

  private Integer intAt(JsonNode node, String field) {
    JsonNode child = node == null ? null : node.get(field);
    return child != null && child.isNumber() ? child.asInt() : null;
  }
}
