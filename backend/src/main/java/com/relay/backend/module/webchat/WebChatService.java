package com.relay.backend.module.webchat;

import com.relay.backend.common.error.AppException;
import com.relay.backend.common.error.ErrorCode;
import com.relay.backend.module.webchat.dto.WebChatMessageRequest;
import com.relay.backend.module.webchat.dto.WebChatMessageResponse;
import com.relay.backend.module.webchat.dto.WebChatSessionResponse;
import java.awt.image.BufferedImage;
import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.WebSocket;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.TimeUnit;
import javax.imageio.ImageIO;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

@Service
public class WebChatService {

  private static final String ROOT_PARENT_MESSAGE_ID = "client-created-root";
  private static final String DEFAULT_MODEL = "gpt-5-3";
  private static final String DEFAULT_USER_AGENT =
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
          + "AppleWebKit/537.36 (KHTML, like Gecko) "
          + "Chrome/147.0.0.0 Safari/537.36";
  private static final String DEFAULT_OAI_CLIENT_BUILD_NUMBER = "5561002";
  private static final String DEFAULT_OAI_CLIENT_VERSION =
      "prod-8bd5c4ba133b610a0563c545f5e81318b3890627";
  private static final Set<String> TEXT_DELTA_TYPES =
      Set.of("response.output_text.delta", "response.refusal.delta");
  private static final Set<String> TEXT_DONE_TYPES =
      Set.of("response.output_text.done", "response.refusal.done");
  private static final Set<String> DONE_TYPES =
      Set.of(
          "message_stream_complete",
          "response.completed",
          "response.failed",
          "response.incomplete",
          "response.cancelled",
          "done");
  private static final Set<String> SUPPORTED_IMAGE_MEDIA_TYPES =
      Set.of("image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif");
  private static final Set<String> OUTPUT_TEXT_TYPES =
      Set.of("output_text", "text", "refusal");
  private static final int MAX_IMAGE_BYTES = 10 * 1024 * 1024;

  private final WebChatRepository repository;
  private final ObjectMapper objectMapper;
  private final HttpClient httpClient =
      HttpClient.newBuilder()
          .connectTimeout(Duration.ofSeconds(30))
          .version(HttpClient.Version.HTTP_1_1)
          .build();

  public WebChatService(WebChatRepository repository, ObjectMapper objectMapper) {
    this.repository = repository;
    this.objectMapper = objectMapper;
  }

  public interface StreamSink {
    void delta(String delta);

    void replace(String text);
  }

  public WebChatSessionResponse session(UUID userId) {
    WebChatSession session = findOrCreateSession(userId);
    WebChatModelConfig config = session.config();
    return new WebChatSessionResponse(
        config.id(),
        config.name(),
        firstNonBlank(config.model(), DEFAULT_MODEL),
        session.conversationId(),
        session.conversationId() != null && !session.conversationId().isBlank());
  }

  public WebChatSessionResponse reset(UUID userId) {
    WebChatSession session = findOrCreateSession(userId);
    WebChatSession reset =
        repository.saveSession(
            userId, session.configId(), null, ROOT_PARENT_MESSAGE_ID, Instant.now());
    return new WebChatSessionResponse(
        reset.config().id(),
        reset.config().name(),
        firstNonBlank(reset.config().model(), DEFAULT_MODEL),
        reset.conversationId(),
        false);
  }

  public WebChatMessageResponse send(UUID userId, WebChatMessageRequest request) {
    return sendInternal(userId, request, null);
  }

  public WebChatMessageResponse stream(UUID userId, WebChatMessageRequest request, StreamSink streamSink) {
    return sendInternal(userId, request, streamSink);
  }

  private WebChatMessageResponse sendInternal(
      UUID userId, WebChatMessageRequest request, StreamSink streamSink) {
    String message = request.message() == null ? "" : request.message().trim();
    List<WebChatMessageRequest.ImageAttachment> imageRequests =
        request.images() == null ? List.of() : request.images();
    if (message.isBlank() && imageRequests.isEmpty()) {
      throw new AppException(
          ErrorCode.VALIDATION_FAILED,
          "Message or image is required",
          HttpStatus.BAD_REQUEST);
    }

    WebChatSession session = findOrCreateSession(userId);
    WebChatModelConfig config = session.config();
    boolean newConversation = Boolean.TRUE.equals(request.newConversation());
    String conversationId = newConversation ? null : blankToNull(session.conversationId());
    String parentMessageId =
        newConversation ? ROOT_PARENT_MESSAGE_ID : firstNonBlank(session.parentMessageId(), ROOT_PARENT_MESSAGE_ID);
    String model = firstNonBlank(request.model(), firstNonBlank(config.model(), DEFAULT_MODEL));

    String conduitToken = config.conduitToken();
    if (config.callPrepare()) {
      conduitToken = prepareTurn(config, message, model, conversationId, parentMessageId);
    }
    if (conduitToken == null || conduitToken.isBlank()) {
      throw new AppException(
          ErrorCode.VALIDATION_FAILED,
          "Web chat config requires conduit_token or call_prepare=true",
          HttpStatus.SERVICE_UNAVAILABLE);
    }

    List<UploadedImage> images = uploadImages(config, imageRequests);
    TurnResult result =
        sendTurn(config, message, model, conversationId, parentMessageId, conduitToken, images, streamSink);
    String nextConversationId = firstNonBlank(result.conversationId(), conversationId);
    String nextParentMessageId = firstNonBlank(result.parentMessageId(), parentMessageId);
    repository.saveSession(userId, config.id(), nextConversationId, nextParentMessageId, Instant.now());

    return new WebChatMessageResponse(
        result.answer(),
        nextConversationId,
        nextParentMessageId,
        model,
        config.id(),
        config.name());
  }

  private WebChatSession findOrCreateSession(UUID userId) {
    WebChatSession existing = repository.findSession(userId).orElse(null);
    if (existing != null && existing.config() != null && existing.config().enabled()) {
      return existing;
    }

    List<WebChatModelConfig> configs = repository.findEnabledConfigs();
    if (configs.isEmpty()) {
      throw new AppException(
          ErrorCode.NOT_FOUND,
          "No web chat model config is enabled",
          HttpStatus.NOT_FOUND);
    }
    WebChatModelConfig config = configs.get(Math.floorMod(userId.hashCode(), configs.size()));
    return repository.saveSession(userId, config.id(), null, ROOT_PARENT_MESSAGE_ID, Instant.now());
  }

  private String prepareTurn(
      WebChatModelConfig config,
      String message,
      String model,
      String conversationId,
      String parentMessageId) {
    String path = "/backend-api/f/conversation/prepare";
    Map<String, Object> payload = new LinkedHashMap<>();
    payload.put("action", "next");
    payload.put("fork_from_shared_post", false);
    payload.put("parent_message_id", parentMessageId);
    payload.put("model", model);
    payload.put("client_prepare_state", conversationId == null ? "sent" : "none");
    payload.put("timezone_offset_min", -480);
    payload.put("timezone", "Asia/Shanghai");
    payload.put("conversation_mode", Map.of("kind", "primary_assistant"));
    payload.put("system_hints", List.of());
    payload.put("supports_buffering", true);
    payload.put("supported_encodings", List.of("v1"));
    payload.put("client_contextual_info", Map.of("app_name", "chatgpt.com"));
    if (conversationId != null) {
      payload.put("conversation_id", conversationId);
    } else {
      payload.put(
          "partial_query",
          Map.of(
              "id",
              UUID.randomUUID().toString(),
              "author",
              Map.of("role", "user"),
              "content",
              Map.of("content_type", "text", "parts", List.of(message))));
    }

    JsonNode response = sendJson(config, path, payload, conversationId, "*/*", null);
    String token = textAt(response, "conduit_token");
    if (token == null || token.isBlank()) {
      throw new AppException(
          ErrorCode.INTERNAL_ERROR,
          "Web chat prepare did not return conduit_token",
          HttpStatus.BAD_GATEWAY);
    }
    return token;
  }

  private List<UploadedImage> uploadImages(
      WebChatModelConfig config, List<WebChatMessageRequest.ImageAttachment> imageRequests) {
    if (imageRequests.isEmpty()) {
      return List.of();
    }
    List<UploadedImage> uploaded = new ArrayList<>();
    for (WebChatMessageRequest.ImageAttachment imageRequest : imageRequests) {
      uploaded.add(uploadImage(config, normalizeImage(imageRequest)));
    }
    return uploaded;
  }

  private UploadImage normalizeImage(WebChatMessageRequest.ImageAttachment request) {
    if (request == null) {
      throw new AppException(ErrorCode.VALIDATION_FAILED, "Image is required", HttpStatus.BAD_REQUEST);
    }
    String mediaType = normalizeMediaType(request.mediaType());
    if (!SUPPORTED_IMAGE_MEDIA_TYPES.contains(mediaType)) {
      throw new AppException(
          ErrorCode.VALIDATION_FAILED,
          "Unsupported image media type: " + firstNonBlank(mediaType, "<empty>"),
          HttpStatus.BAD_REQUEST);
    }
    String encoded = firstNonBlank(request.data(), "");
    int comma = encoded.indexOf(',');
    if (encoded.startsWith("data:") && comma >= 0) {
      encoded = encoded.substring(comma + 1);
    }
    byte[] bytes;
    try {
      bytes = Base64.getDecoder().decode(encoded.replaceAll("\\s+", ""));
    } catch (IllegalArgumentException exception) {
      throw new AppException(
          ErrorCode.VALIDATION_FAILED, "Image data must be valid base64", HttpStatus.BAD_REQUEST);
    }
    if (bytes.length == 0 || bytes.length > MAX_IMAGE_BYTES) {
      throw new AppException(
          ErrorCode.VALIDATION_FAILED,
          "Image size must be between 1 byte and 10 MB",
          HttpStatus.BAD_REQUEST);
    }

    int width = request.width() == null ? 0 : request.width();
    int height = request.height() == null ? 0 : request.height();
    if (width <= 0 || height <= 0) {
      int[] dimensions = readImageDimensions(bytes);
      width = dimensions[0];
      height = dimensions[1];
    }
    if (width <= 0 || height <= 0) {
      throw new AppException(
          ErrorCode.VALIDATION_FAILED,
          "Image width and height are required",
          HttpStatus.BAD_REQUEST);
    }

    String name = firstNonBlank(request.name(), UUID.randomUUID() + imageExtension(mediaType));
    return new UploadImage(bytes, mediaType, name, bytes.length, width, height);
  }

  private UploadedImage uploadImage(WebChatModelConfig config, UploadImage image) {
    Map<String, Object> createPayload = new LinkedHashMap<>();
    createPayload.put("file_name", image.name());
    createPayload.put("file_size", image.size());
    createPayload.put("use_case", "multimodal");
    createPayload.put("timezone_offset_min", -480);
    createPayload.put("reset_rate_limits", false);
    createPayload.put("store_in_library", true);
    JsonNode created = sendJson(config, "/backend-api/files", createPayload, null, "application/json", null);
    String fileId = textAt(created, "file_id");
    String uploadUrl = textAt(created, "upload_url");
    if (fileId == null || uploadUrl == null) {
      throw new AppException(
          ErrorCode.INTERNAL_ERROR,
          "Unexpected image upload create response",
          HttpStatus.BAD_GATEWAY);
    }

    uploadRawImage(config, uploadUrl, image.bytes(), image.mediaType());
    String libraryFileId = processUploadedFile(config, fileId, image.name());
    return new UploadedImage(
        fileId, libraryFileId, image.name(), image.mediaType(), image.size(), image.width(), image.height());
  }

  private void uploadRawImage(
      WebChatModelConfig config, String uploadUrl, byte[] bytes, String mediaType) {
    HttpRequest request =
        HttpRequest.newBuilder(URI.create(uploadUrl))
            .timeout(Duration.ofMinutes(2))
            .header(HttpHeaders.CONTENT_TYPE, mediaType)
            .header("origin", trimTrailingSlash(firstNonBlank(config.baseUrl(), "https://chatgpt.com")))
            .header("referer", trimTrailingSlash(firstNonBlank(config.baseUrl(), "https://chatgpt.com")) + "/")
            .header("x-ms-blob-type", "BlockBlob")
            .header("user-agent", firstNonBlank(config.userAgent(), DEFAULT_USER_AGENT))
            .PUT(HttpRequest.BodyPublishers.ofByteArray(bytes))
            .build();
    HttpResponse<InputStream> response = send(request);
    if (response.statusCode() != 200 && response.statusCode() != 201) {
      throw upstreamError(response);
    }
    try (InputStream ignored = response.body()) {
      // Drain response body.
    } catch (Exception ignored) {
      // Upload already succeeded.
    }
  }

  private String processUploadedFile(WebChatModelConfig config, String fileId, String fileName) {
    Map<String, Object> payload = new LinkedHashMap<>();
    payload.put("file_id", fileId);
    payload.put("use_case", "multimodal");
    payload.put("index_for_retrieval", false);
    payload.put("file_name", fileName);
    payload.put("metadata", Map.of("store_in_library", true));

    String path = "/backend-api/files/process_upload_stream";
    HttpRequest.Builder builder =
        HttpRequest.newBuilder(URI.create(joinUrl(config.baseUrl(), path)))
            .timeout(Duration.ofMinutes(2))
            .POST(HttpRequest.BodyPublishers.ofString(writeJson(payload), StandardCharsets.UTF_8));
    applyHeaders(builder, config, path, null, "text/event-stream", null);
    HttpResponse<InputStream> response = send(builder.build());
    updateConfigFromResponse(config, response);
    if (response.statusCode() < 200 || response.statusCode() >= 300) {
      throw upstreamError(response);
    }

    String libraryFileId = null;
    try (BufferedReader reader =
        new BufferedReader(new InputStreamReader(response.body(), StandardCharsets.UTF_8))) {
      String line;
      while ((line = reader.readLine()) != null) {
        line = line.trim();
        if (line.isEmpty()) {
          continue;
        }
        if (line.startsWith("data:")) {
          line = line.substring(5).trim();
        }
        JsonNode event;
        try {
          event = objectMapper.readTree(line);
        } catch (Exception ignored) {
          continue;
        }
        String metadataObjectId = textAt(event.path("extra"), "metadata_object_id");
        if (metadataObjectId != null) {
          libraryFileId = metadataObjectId;
        }
        if ("file.processing.failed".equals(textAt(event, "event"))) {
          throw new AppException(
              ErrorCode.INTERNAL_ERROR,
              firstNonBlank(textAt(event, "message"), "Failed processing uploaded image"),
              HttpStatus.BAD_GATEWAY);
        }
      }
    } catch (AppException exception) {
      throw exception;
    } catch (Exception exception) {
      throw new AppException(
          ErrorCode.INTERNAL_ERROR,
          "Unable to process uploaded image: " + exceptionSummary(exception),
          HttpStatus.BAD_GATEWAY);
    }
    return libraryFileId;
  }

  private TurnResult sendTurn(
      WebChatModelConfig config,
      String message,
      String model,
      String conversationId,
      String parentMessageId,
      String conduitToken,
      List<UploadedImage> images,
      StreamSink streamSink) {
    String path = "/backend-api/f/conversation";
    updateLastUsedModelConfig(config, model, conversationId);
    Map<String, Object> payload = conversationPayload(message, model, conversationId, parentMessageId, images);
    String body = writeJson(payload);
    HttpRequest.Builder builder =
        HttpRequest.newBuilder(URI.create(joinUrl(config.baseUrl(), path)))
            .timeout(Duration.ofMinutes(3))
            .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8));
    applyHeaders(builder, config, path, conversationId, "text/event-stream", conduitToken);

    HttpResponse<InputStream> response = send(builder.build());
    updateConfigFromResponse(config, response);
    if (response.statusCode() < 200 || response.statusCode() >= 300) {
      throw upstreamError(response);
    }

    String answer = "";
    String resultConversationId = conversationId;
    String assistantMessageId = null;
    String topicId = null;
    String resumeToken = null;
    try (BufferedReader reader =
        new BufferedReader(new InputStreamReader(response.body(), StandardCharsets.UTF_8))) {
      String line;
      while ((line = reader.readLine()) != null) {
        JsonNode event = parseSseDataLine(line);
        if (event == null) {
          continue;
        }
        if (isDoneEvent(event)) {
          break;
        }
        String nextAnswer = applyEvent(answer, event);
        if (nextAnswer != null) {
          emitAnswerChange(answer, nextAnswer, streamSink);
          answer = nextAnswer;
        }
        String type = textAt(event, "type");
        if ("resume_conversation_token".equals(type)) {
          resumeToken = firstNonBlank(textAt(event, "token"), resumeToken);
          topicId = firstNonBlank(topicIdFromResumeToken(resumeToken), topicId);
        }
        String eventConversationId = textAt(event, "conversation_id");
        if (eventConversationId != null && !eventConversationId.isBlank()) {
          resultConversationId = eventConversationId;
        }
        topicId = firstNonBlank(extractTopicId(event), topicId);
        assistantMessageId = firstNonBlank(extractAssistantMessageId(event), assistantMessageId);
        if (type != null && DONE_TYPES.contains(type)) {
          break;
        }
      }
    } catch (Exception exception) {
      if (answer != null && !answer.isBlank()) {
        return new TurnResult(answer, resultConversationId, assistantMessageId);
      }
      throw new AppException(
          ErrorCode.INTERNAL_ERROR,
          "读取网页对话响应失败：" + exceptionSummary(exception),
          HttpStatus.BAD_GATEWAY);
    }

    if (topicId == null || topicId.isBlank()) {
      topicId = topicIdFromResumeToken(resumeToken);
    }
    if ((answer == null || answer.isBlank()) && topicId != null && !topicId.isBlank()) {
      WsTurnResult wsResult = readHandoffTopic(config, topicId, resultConversationId, streamSink);
      answer = firstNonBlank(wsResult.answer(), answer);
      assistantMessageId = firstNonBlank(wsResult.assistantMessageId(), assistantMessageId);
    }

    return new TurnResult(answer, resultConversationId, assistantMessageId);
  }

  private JsonNode sendJson(
      WebChatModelConfig config,
      String path,
      Map<String, Object> payload,
      String conversationId,
      String accept,
      String conduitToken) {
    String body = writeJson(payload);
    HttpRequest.Builder builder =
        HttpRequest.newBuilder(URI.create(joinUrl(config.baseUrl(), path)))
            .timeout(Duration.ofMinutes(2))
            .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8));
    applyHeaders(builder, config, path, conversationId, accept, conduitToken);
    HttpResponse<InputStream> response = send(builder.build());
    updateConfigFromResponse(config, response);
    if (response.statusCode() < 200 || response.statusCode() >= 300) {
      throw upstreamError(response);
    }
    try (InputStream inputStream = response.body()) {
      return objectMapper.readTree(inputStream);
    } catch (Exception exception) {
      throw new AppException(
          ErrorCode.INTERNAL_ERROR,
          "Unable to parse web chat response",
          HttpStatus.BAD_GATEWAY);
    }
  }

  private void updateLastUsedModelConfig(WebChatModelConfig config, String model, String conversationId) {
    String path = "/backend-api/settings/user_last_used_model_config";
    String encodedModel = URLEncoder.encode(model, StandardCharsets.UTF_8);
    HttpRequest.Builder builder =
        HttpRequest.newBuilder(URI.create(joinUrl(config.baseUrl(), path) + "?model_slug=" + encodedModel))
            .timeout(Duration.ofSeconds(30))
            .method("PATCH", HttpRequest.BodyPublishers.ofString("{}", StandardCharsets.UTF_8));
    applyHeaders(builder, config, path, conversationId, "application/json", null);
    try {
      HttpResponse<InputStream> response = send(builder.build());
      updateConfigFromResponse(config, response);
      try (InputStream ignored = response.body()) {
        // Drain the response body so the HTTP connection can be reused.
      } catch (Exception ignored) {
        // This metadata update succeeded already; response draining is best effort.
      }
    } catch (Exception ignored) {
      // Same as the reference openai_compat_api flow: this preference update is best effort.
    }
  }

  private WsTurnResult readHandoffTopic(
      WebChatModelConfig config, String topicId, String conversationId, StreamSink streamSink) {
    String wsUrl = fetchWebsocketUrl(config, conversationId);
    TopicWebSocketListener listener = new TopicWebSocketListener(topicId, streamSink);
    try {
      WebSocket webSocket =
          httpClient
              .newWebSocketBuilder()
              .header("Origin", trimTrailingSlash(firstNonBlank(config.baseUrl(), "https://chatgpt.com")))
              .header("User-Agent", firstNonBlank(config.userAgent(), DEFAULT_USER_AGENT))
              .connectTimeout(Duration.ofSeconds(30))
              .buildAsync(URI.create(wsUrl), listener)
              .get(30, TimeUnit.SECONDS);
      webSocket.sendText(writeJson(websocketSubscribeFrame(topicId)), true).join();
      WsTurnResult result = listener.result().get(180, TimeUnit.SECONDS);
      webSocket.sendClose(WebSocket.NORMAL_CLOSURE, "done");
      return result;
    } catch (Exception exception) {
      throw new AppException(
          ErrorCode.INTERNAL_ERROR,
          "读取网页对话 WebSocket 响应失败：" + exceptionSummary(exception),
          HttpStatus.BAD_GATEWAY);
    }
  }

  private String fetchWebsocketUrl(WebChatModelConfig config, String conversationId) {
    String path = "/backend-api/celsius/ws/user";
    HttpRequest.Builder builder =
        HttpRequest.newBuilder(URI.create(joinUrl(config.baseUrl(), path)))
            .timeout(Duration.ofSeconds(30))
            .GET();
    applyHeaders(builder, config, path, conversationId, "*/*", null);
    HttpResponse<InputStream> response = send(builder.build());
    updateConfigFromResponse(config, response);
    if (response.statusCode() < 200 || response.statusCode() >= 300) {
      throw upstreamError(response);
    }
    try (InputStream inputStream = response.body()) {
      String wsUrl = textAt(objectMapper.readTree(inputStream), "websocket_url");
      if (wsUrl == null || !(wsUrl.startsWith("ws://") || wsUrl.startsWith("wss://"))) {
        throw new IllegalStateException("websocket_url missing from upstream response");
      }
      return wsUrl;
    } catch (Exception exception) {
      throw new AppException(
          ErrorCode.INTERNAL_ERROR,
          "Unable to parse web chat websocket response: " + exceptionSummary(exception),
          HttpStatus.BAD_GATEWAY);
    }
  }

  private List<Map<String, Object>> websocketSubscribeFrame(String topicId) {
    return List.of(
        Map.of(
            "id",
            1,
            "command",
            Map.of(
                "type",
                "connect",
                "presence",
                Map.of("type", "presence", "state", "background"))),
        Map.of("id", 2, "command", Map.of("type", "subscribe", "topic_id", "conversations")),
        Map.of("id", 3, "command", Map.of("type", "subscribe", "topic_id", "app_notifications")),
        Map.of("id", 4, "command", Map.of("type", "subscribe", "topic_id", topicId)));
  }

  private Map<String, Object> conversationPayload(
      String message,
      String model,
      String conversationId,
      String parentMessageId,
      List<UploadedImage> images) {
    Map<String, Object> metadata = new LinkedHashMap<>();
    metadata.put("developer_mode_connector_ids", List.of());
    metadata.put("selected_connector_ids", List.of());
    metadata.put("selected_sync_knowledge_store_ids", List.of());
    metadata.put("selected_sources", List.of());
    metadata.put("selected_github_repos", List.of());
    metadata.put("selected_all_github_repos", false);
    metadata.put("serialization_metadata", Map.of("custom_symbol_offsets", List.of()));
    Map<String, Object> content = messageContent(message, images);
    if (!images.isEmpty()) {
      metadata.put("attachments", imageAttachments(images));
    }

    Map<String, Object> userMessage = new LinkedHashMap<>();
    userMessage.put("id", UUID.randomUUID().toString());
    userMessage.put("author", Map.of("role", "user"));
    userMessage.put("create_time", System.currentTimeMillis() / 1000.0);
    userMessage.put("content", content);
    userMessage.put("metadata", metadata);

    Map<String, Object> payload = new LinkedHashMap<>();
    payload.put("action", "next");
    payload.put("messages", List.of(userMessage));
    payload.put("parent_message_id", parentMessageId);
    payload.put("model", model);
    payload.put("timezone_offset_min", -480);
    payload.put("timezone", "Asia/Shanghai");
    payload.put("conversation_mode", Map.of("kind", "primary_assistant"));
    payload.put("enable_message_followups", true);
    payload.put("system_hints", List.of());
    payload.put("supports_buffering", true);
    payload.put("supported_encodings", List.of("v1"));
    payload.put(
        "client_contextual_info",
        Map.of(
            "is_dark_mode",
            false,
            "time_since_loaded",
            1,
            "page_height",
            703,
            "page_width",
            1008,
            "pixel_ratio",
            1.25,
            "screen_height",
            864,
            "screen_width",
            1536,
            "app_name",
            "chat.sharedchat.cc"));
    payload.put("paragen_cot_summary_display_override", "allow");
    payload.put("force_parallel_switch", "auto");
    if (model.contains("thinking") || model.endsWith("-pro")) {
      payload.put("thinking_effort", "extended");
    }
    if (conversationId != null) {
      payload.put("conversation_id", conversationId);
    }
    return payload;
  }

  private Map<String, Object> messageContent(String message, List<UploadedImage> images) {
    if (images.isEmpty()) {
      return Map.of("content_type", "text", "parts", List.of(message));
    }
    List<Object> parts = new ArrayList<>();
    for (UploadedImage image : images) {
      Map<String, Object> imagePart = new LinkedHashMap<>();
      imagePart.put("content_type", "image_asset_pointer");
      imagePart.put("asset_pointer", "sediment://" + image.fileId());
      imagePart.put("size_bytes", image.size());
      imagePart.put("width", image.width());
      imagePart.put("height", image.height());
      parts.add(imagePart);
    }
    parts.add(message);
    return Map.of("content_type", "multimodal_text", "parts", parts);
  }

  private List<Map<String, Object>> imageAttachments(List<UploadedImage> images) {
    List<Map<String, Object>> attachments = new ArrayList<>();
    for (UploadedImage image : images) {
      Map<String, Object> attachment = new LinkedHashMap<>();
      attachment.put("id", image.fileId());
      attachment.put("size", image.size());
      attachment.put("name", image.name());
      attachment.put("mime_type", image.mediaType());
      attachment.put("width", image.width());
      attachment.put("height", image.height());
      attachment.put("source", "local");
      attachment.put("is_big_paste", false);
      if (image.libraryFileId() != null && !image.libraryFileId().isBlank()) {
        attachment.put("library_file_id", image.libraryFileId());
      }
      attachments.add(attachment);
    }
    return attachments;
  }

  private void applyHeaders(
      HttpRequest.Builder builder,
      WebChatModelConfig config,
      String path,
      String conversationId,
      String accept,
      String conduitToken) {
    String baseUrl = trimTrailingSlash(firstNonBlank(config.baseUrl(), "https://chatgpt.com"));
    String referer = conversationId == null ? baseUrl + "/" : baseUrl + "/c/" + conversationId;
    builder.header(HttpHeaders.ACCEPT, accept);
    builder.header(HttpHeaders.CONTENT_TYPE, "application/json");
    builder.header("oai-language", "zh-CN");
    builder.header("origin", baseUrl);
    builder.header("referer", referer);
    builder.header("user-agent", firstNonBlank(config.userAgent(), DEFAULT_USER_AGENT));
    builder.header("x-oai-turn-trace-id", UUID.randomUUID().toString());
    builder.header("x-openai-target-path", path);
    builder.header("x-openai-target-route", path);
    putHeaderIfPresent(builder, HttpHeaders.AUTHORIZATION, authorization(config));
    putHeaderIfPresent(builder, "chatgpt-account-id", config.accountId());
    putHeaderIfPresent(builder, "cookie", config.cookie());
    putHeaderIfPresent(
        builder, "oai-client-build-number", firstNonBlank(config.oaiClientBuildNumber(), DEFAULT_OAI_CLIENT_BUILD_NUMBER));
    putHeaderIfPresent(
        builder, "oai-client-version", firstNonBlank(config.oaiClientVersion(), DEFAULT_OAI_CLIENT_VERSION));
    putHeaderIfPresent(builder, "oai-device-id", config.oaiDeviceId());
    putHeaderIfPresent(builder, "oai-session-id", config.oaiSessionId());
    putHeaderIfPresent(builder, "openai-sentinel-chat-requirements-token", config.sentinelToken());
    putHeaderIfPresent(builder, "x-oai-is", config.oaiIs());
    putHeaderIfPresent(builder, "x-conduit-token", conduitToken);
  }

  private String authorization(WebChatModelConfig config) {
    if (config.authHeader() != null && !config.authHeader().isBlank()) {
      return config.authHeader().trim();
    }
    if (config.bearerToken() == null || config.bearerToken().isBlank()) {
      return null;
    }
    String token = config.bearerToken().trim();
    return token.toLowerCase(Locale.ROOT).startsWith("bearer ") ? token : "Bearer " + token;
  }

  private void putHeaderIfPresent(HttpRequest.Builder builder, String name, String value) {
    if (value != null && !value.isBlank() && !value.startsWith("PASTE_")) {
      builder.header(name, value.trim());
    }
  }

  private HttpResponse<InputStream> send(HttpRequest request) {
    try {
      return httpClient.send(request, HttpResponse.BodyHandlers.ofInputStream());
    } catch (InterruptedException exception) {
      Thread.currentThread().interrupt();
      throw new AppException(ErrorCode.INTERNAL_ERROR, "Web chat request interrupted", HttpStatus.BAD_GATEWAY);
    } catch (Exception exception) {
      String path = request.uri() == null ? "<unknown>" : request.uri().getPath();
      throw new AppException(
          ErrorCode.INTERNAL_ERROR,
          "Unable to reach web chat upstream " + path + ": " + exceptionSummary(exception),
          HttpStatus.BAD_GATEWAY);
    }
  }

  private AppException upstreamError(HttpResponse<InputStream> response) {
    String body = "";
    try (InputStream inputStream = response.body()) {
      body = new String(inputStream.readAllBytes(), StandardCharsets.UTF_8);
    } catch (Exception ignored) {
      body = "";
    }
    String message = body.isBlank() ? "Web chat upstream returned HTTP " + response.statusCode() : body;
    if (message.length() > 1000) {
      message = message.substring(0, 1000);
    }
    return new AppException(ErrorCode.INTERNAL_ERROR, message, HttpStatus.BAD_GATEWAY);
  }

  private void updateConfigFromResponse(WebChatModelConfig config, HttpResponse<?> response) {
    response.headers().firstValue("x-oai-is-update")
        .ifPresent(value -> repository.updateConfigRuntimeState(config.id(), value, Instant.now()));
  }

  private JsonNode parseSseDataLine(String line) {
    if (line == null || !line.startsWith("data:")) {
      return null;
    }
    String data = line.substring(5).trim();
    if (data.isEmpty()) {
      return null;
    }
    if ("[DONE]".equals(data)) {
      return objectMapper.valueToTree("[DONE]");
    }
    try {
      return objectMapper.readTree(data);
    } catch (Exception exception) {
      return null;
    }
  }

  private List<JsonNode> parseEncodedSse(String encodedItem) {
    List<JsonNode> events = new ArrayList<>();
    List<String> dataLines = new ArrayList<>();
    for (String rawLine : encodedItem.split("\\R")) {
      String line = rawLine.trim();
      if (line.isEmpty()) {
        addEncodedSseEvent(events, dataLines);
        dataLines.clear();
        continue;
      }
      if (line.startsWith("data:")) {
        dataLines.add(line.substring(5).trim());
      }
    }
    addEncodedSseEvent(events, dataLines);
    return events;
  }

  private void addEncodedSseEvent(List<JsonNode> events, List<String> dataLines) {
    if (dataLines.isEmpty()) {
      return;
    }
    String data = String.join("\n", dataLines);
    if ("[DONE]".equals(data)) {
      events.add(objectMapper.valueToTree("[DONE]"));
      return;
    }
    try {
      events.add(objectMapper.readTree(data));
    } catch (Exception ignored) {
      // Ignore non-JSON status frames; only model events can update the answer.
    }
  }

  private List<String> extractEncodedItems(JsonNode node) {
    List<String> items = new ArrayList<>();
    collectEncodedItems(node, null, items);
    return items;
  }

  private void collectEncodedItems(JsonNode node, String fieldName, List<String> items) {
    if (node == null || node.isNull()) {
      return;
    }
    if ("encoded_item".equals(fieldName) && node.isTextual()) {
      items.add(node.asText());
      return;
    }
    if (fieldName == null && node.isTextual() && node.asText().contains("data:")) {
      items.add(node.asText());
      return;
    }
    if (node.isArray()) {
      for (JsonNode child : node) {
        collectEncodedItems(child, null, items);
      }
      return;
    }
    if (node.isObject()) {
      node.properties().forEach(entry -> collectEncodedItems(entry.getValue(), entry.getKey(), items));
    }
  }

  private boolean isWsDoneMessage(JsonNode node) {
    if (node == null || !node.isArray()) {
      return false;
    }
    for (JsonNode item : node) {
      JsonNode nested = item.path("payload").path("payload");
      if ("done".equals(textAt(nested, "type"))) {
        return true;
      }
    }
    return false;
  }

  private String applyEvent(String answer, JsonNode event) {
    String eventType = textAt(event, "type");
    if (containsText(TEXT_DELTA_TYPES, eventType)) {
      return answer + firstNonBlank(textAt(event, "delta"), "");
    }
    if (containsText(TEXT_DONE_TYPES, eventType)) {
      return mergeFullText(answer, textAt(event, "text"));
    }
    if ("response.content_part.done".equals(eventType)) {
      String text = textAt(event.path("part"), "text");
      return text == null ? answer : mergeFullText(answer, text);
    }
    if ("response.output_item.done".equals(eventType)
        || "response.function_call_arguments.done".equals(eventType)) {
      String text = extractOutputItemText(event.path("item"));
      return text == null ? answer : mergeFullText(answer, text);
    }
    if ("response.completed".equals(eventType)) {
      String text = extractOutputText(event.path("response").path("output"));
      return text == null ? answer : mergeFullText(answer, text);
    }
    String fullText = extractAssistantMessageText(event);
    if (fullText != null) {
      return mergeFullText(answer, fullText);
    }
    if (isPatchOperation(event) && !"patch".equals(textAt(event, "o"))) {
      return applyPatchOperation(answer, event);
    }
    JsonNode value = event.get("v");
    if (value == null || value.isNull()) {
      return answer;
    }
    if (value.isTextual() && !isPatchOperation(event)) {
      return answer + value.asText();
    }
    if (value.isArray()) {
      String updated = answer;
      for (JsonNode patch : value) {
        if (isPatchOperation(patch)) {
          updated = applyPatchOperation(updated, patch);
        }
      }
      return updated;
    }
    return answer;
  }

  private void emitAnswerChange(String answer, String nextAnswer, StreamSink streamSink) {
    if (streamSink == null || nextAnswer == null || nextAnswer.equals(answer)) {
      return;
    }
    String current = answer == null ? "" : answer;
    if (nextAnswer.startsWith(current)) {
      String delta = nextAnswer.substring(current.length());
      if (!delta.isEmpty()) {
        streamSink.delta(delta);
      }
      return;
    }
    streamSink.replace(nextAnswer);
  }

  private String extractTopicId(JsonNode event) {
    String topicId = textAt(event, "topic_id");
    if (topicId != null) {
      return topicId;
    }
    JsonNode options = event.path("options");
    if (options.isArray()) {
      for (JsonNode option : options) {
        topicId = textAt(option, "topic_id");
        if (topicId != null) {
          return topicId;
        }
      }
    }
    topicId = topicIdFromResumeToken(textAt(event, "resume_token"));
    if (topicId != null) {
      return topicId;
    }
    topicId = topicIdFromResumeToken(textAt(event, "token"));
    if (topicId != null) {
      return topicId;
    }
    return null;
  }

  private String topicIdFromResumeToken(String token) {
    if (token == null || token.isBlank()) {
      return null;
    }
    String[] parts = token.split("\\.");
    if (parts.length < 2) {
      return null;
    }
    try {
      String payload = parts[1];
      int padding = Math.floorMod(-payload.length(), 4);
      if (padding > 0) {
        payload += "=".repeat(padding);
      }
      byte[] decoded = Base64.getUrlDecoder().decode(payload);
      JsonNode node = objectMapper.readTree(new String(decoded, StandardCharsets.UTF_8));
      return firstNonBlank(textAt(node, "turn_topic_id"), textAt(node, "topic_id"));
    } catch (Exception exception) {
      return null;
    }
  }

  private String extractOutputText(JsonNode output) {
    if (output == null || !output.isArray()) {
      return null;
    }
    List<String> parts = new ArrayList<>();
    for (JsonNode item : output) {
      String text = extractOutputItemText(item);
      if (text != null) {
        parts.add(text);
      }
    }
    return parts.isEmpty() ? null : String.join("", parts);
  }

  private String extractOutputItemText(JsonNode item) {
    if (item == null || item.isNull()) {
      return null;
    }
    String directText = textAt(item, "text");
    if (directText != null) {
      return directText;
    }
    JsonNode content = item.path("content");
    if (!content.isArray()) {
      return null;
    }
    List<String> parts = new ArrayList<>();
    for (JsonNode part : content) {
      String type = textAt(part, "type");
      if (containsText(OUTPUT_TEXT_TYPES, type)) {
        String text = textAt(part, "text");
        if (text != null) {
          parts.add(text);
        }
      }
    }
    return parts.isEmpty() ? null : String.join("", parts);
  }

  private String extractAssistantMessageText(JsonNode event) {
    List<JsonNode> candidates = new ArrayList<>();
    JsonNode message = event.get("message");
    if (message != null && message.isObject()) {
      candidates.add(message);
    }
    JsonNode valueMessage = event.path("v").path("message");
    if (valueMessage.isObject()) {
      candidates.add(valueMessage);
    }
    for (JsonNode candidate : candidates) {
      String role = textAt(candidate.path("author"), "role");
      if (role != null && !"assistant".equals(role)) {
        continue;
      }
      JsonNode parts = candidate.path("content").path("parts");
      if (parts.isArray() && parts.size() > 0 && parts.get(0).isTextual()) {
        return parts.get(0).asText();
      }
    }
    return null;
  }

  private String extractAssistantMessageId(JsonNode event) {
    String responseId = textAt(event.path("response"), "id");
    if (responseId != null) {
      return responseId;
    }
    String itemId = textAt(event, "item_id");
    if (itemId != null) {
      return itemId;
    }
    itemId = textAt(event.path("item"), "id");
    if (itemId != null) {
      return itemId;
    }
    List<JsonNode> candidates = new ArrayList<>();
    JsonNode message = event.get("message");
    if (message != null && message.isObject()) {
      candidates.add(message);
    }
    JsonNode valueMessage = event.path("v").path("message");
    if (valueMessage.isObject()) {
      candidates.add(valueMessage);
    }
    for (JsonNode candidate : candidates) {
      String role = textAt(candidate.path("author"), "role");
      if (role != null && !"assistant".equals(role)) {
        continue;
      }
      String id = textAt(candidate, "id");
      if (id != null) {
        return id;
      }
    }
    return null;
  }

  private boolean isPatchOperation(JsonNode value) {
    return value != null
        && value.isObject()
        && textAt(value, "p") != null
        && textAt(value, "o") != null;
  }

  private String applyPatchOperation(String answer, JsonNode operation) {
    String path = textAt(operation, "p");
    String op = textAt(operation, "o");
    JsonNode value = operation.get("v");
    if (path == null || op == null || value == null || value.isNull()) {
      return answer;
    }
    if ("/message/content/parts/0".equals(path)) {
      if ("append".equals(op) && value.isTextual()) {
        return answer + value.asText();
      }
      if (Set.of("replace", "add").contains(op) && value.isTextual()) {
        return mergeFullText(answer, value.asText());
      }
    }
    if ("/message/content/parts".equals(path)
        && Set.of("replace", "add").contains(op)
        && value.isArray()
        && value.size() > 0
        && value.get(0).isTextual()) {
      return mergeFullText(answer, value.get(0).asText());
    }
    if ("/message".equals(path) && Set.of("replace", "add").contains(op) && value.isObject()) {
      String text = extractAssistantMessageText(objectMapper.valueToTree(Map.of("message", value)));
      return text == null ? answer : mergeFullText(answer, text);
    }
    return answer;
  }

  private String mergeFullText(String answer, String fullText) {
    if (fullText == null || fullText.isBlank()) {
      return answer;
    }
    if (answer == null || answer.isBlank() || fullText.startsWith(answer)) {
      return fullText;
    }
    if (answer.endsWith(fullText)) {
      return answer;
    }
    return answer + "\n\n" + fullText;
  }

  private boolean containsText(Set<String> values, String value) {
    return value != null && values.contains(value);
  }

  private boolean isDoneEvent(JsonNode event) {
    return event != null && event.isTextual() && "[DONE]".equals(event.asText());
  }

  private String textAt(JsonNode node, String field) {
    if (node == null || node.isNull()) {
      return null;
    }
    JsonNode child = node.get(field);
    if (child == null || child.isNull()) {
      return null;
    }
    if (!child.isTextual() && !child.isNumber() && !child.isBoolean()) {
      return null;
    }
    String value = child.asText();
    return value == null || value.isBlank() ? null : value;
  }

  private String writeJson(Object value) {
    try {
      return objectMapper.writeValueAsString(value);
    } catch (Exception exception) {
      throw new IllegalStateException("Unable to write JSON", exception);
    }
  }

  private String exceptionSummary(Exception exception) {
    String message = exception.getMessage();
    if (message == null || message.isBlank()) {
      message = exception.getClass().getSimpleName();
    }
    if (message.length() > 180) {
      message = message.substring(0, 180);
    }
    return message;
  }

  private String joinUrl(String baseUrl, String path) {
    return trimTrailingSlash(firstNonBlank(baseUrl, "https://chatgpt.com")) + path;
  }

  private String trimTrailingSlash(String value) {
    String result = value.trim();
    while (result.endsWith("/")) {
      result = result.substring(0, result.length() - 1);
    }
    return result;
  }

  private String firstNonBlank(String first, String second) {
    return first == null || first.isBlank() ? second : first.trim();
  }

  private String blankToNull(String value) {
    return value == null || value.isBlank() ? null : value;
  }

  private String normalizeMediaType(String mediaType) {
    String normalized = mediaType == null ? "" : mediaType.trim().toLowerCase(Locale.ROOT);
    return "image/jpg".equals(normalized) ? "image/jpeg" : normalized;
  }

  private String imageExtension(String mediaType) {
    return switch (mediaType) {
      case "image/png" -> ".png";
      case "image/jpeg", "image/jpg" -> ".jpg";
      case "image/webp" -> ".webp";
      case "image/gif" -> ".gif";
      default -> ".img";
    };
  }

  private int[] readImageDimensions(byte[] bytes) {
    try {
      BufferedImage image = ImageIO.read(new ByteArrayInputStream(bytes));
      if (image != null) {
        return new int[] {image.getWidth(), image.getHeight()};
      }
    } catch (Exception ignored) {
      // The browser normally sends dimensions; server-side probing is a fallback.
    }
    return new int[] {0, 0};
  }

  private final class TopicWebSocketListener implements WebSocket.Listener {
    private final String topicId;
    private final StreamSink streamSink;
    private final CompletableFuture<WsTurnResult> result = new CompletableFuture<>();
    private final StringBuilder message = new StringBuilder();
    private String answer = "";
    private String assistantMessageId = null;

    private TopicWebSocketListener(String topicId, StreamSink streamSink) {
      this.topicId = topicId;
      this.streamSink = streamSink;
    }

    private CompletableFuture<WsTurnResult> result() {
      return result;
    }

    @Override
    public void onOpen(WebSocket webSocket) {
      WebSocket.Listener.super.onOpen(webSocket);
      webSocket.request(1);
    }

    @Override
    public CompletionStage<?> onText(WebSocket webSocket, CharSequence data, boolean last) {
      message.append(data);
      if (last) {
        handleMessage(message.toString());
        message.setLength(0);
      }
      webSocket.request(1);
      return CompletableFuture.completedFuture(null);
    }

    @Override
    public CompletionStage<?> onClose(WebSocket webSocket, int statusCode, String reason) {
      if (!result.isDone()) {
        result.complete(new WsTurnResult(answer, assistantMessageId));
      }
      return CompletableFuture.completedFuture(null);
    }

    @Override
    public void onError(WebSocket webSocket, Throwable error) {
      if (!result.isDone()) {
        result.completeExceptionally(error);
      }
    }

    private void handleMessage(String text) {
      if (!text.contains(topicId)) {
        return;
      }
      JsonNode root;
      try {
        root = objectMapper.readTree(text);
      } catch (Exception exception) {
        return;
      }
      boolean done = isWsDoneMessage(root);
      for (String encodedItem : extractEncodedItems(root)) {
        for (JsonNode event : parseEncodedSse(encodedItem)) {
          if (isDoneEvent(event)) {
            done = true;
            continue;
          }
          String nextAnswer = applyEvent(answer, event);
          if (nextAnswer != null) {
            emitAnswerChange(answer, nextAnswer, streamSink);
            answer = nextAnswer;
          }
          assistantMessageId = firstNonBlank(extractAssistantMessageId(event), assistantMessageId);
          String type = textAt(event, "type");
          if (type != null && DONE_TYPES.contains(type)) {
            done = true;
          }
        }
      }
      if (done && !result.isDone()) {
        result.complete(new WsTurnResult(answer, assistantMessageId));
      }
    }
  }

  private record TurnResult(String answer, String conversationId, String parentMessageId) {}

  private record WsTurnResult(String answer, String assistantMessageId) {}

  private record UploadImage(
      byte[] bytes, String mediaType, String name, int size, int width, int height) {}

  private record UploadedImage(
      String fileId,
      String libraryFileId,
      String name,
      String mediaType,
      int size,
      int width,
      int height) {}
}
