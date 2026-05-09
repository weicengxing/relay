package com.relay.backend.module.webchat;

import com.relay.backend.common.api.ApiResponse;
import com.relay.backend.common.error.AppException;
import com.relay.backend.common.error.ErrorCode;
import com.relay.backend.module.auth.AuthTokenService;
import com.relay.backend.module.user.UserRepository;
import com.relay.backend.module.webchat.dto.WebChatMessageRequest;
import com.relay.backend.module.webchat.dto.WebChatMessageResponse;
import com.relay.backend.module.webchat.dto.WebChatSessionResponse;
import jakarta.validation.Valid;
import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import org.springframework.http.MediaType;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import tools.jackson.databind.ObjectMapper;

@RestController
@RequestMapping("/api/web-chat")
public class WebChatController {

  private final WebChatService webChatService;
  private final AuthTokenService authTokenService;
  private final ObjectMapper objectMapper;
  private final UserRepository userRepository;

  public WebChatController(
      WebChatService webChatService,
      AuthTokenService authTokenService,
      ObjectMapper objectMapper,
      UserRepository userRepository) {
    this.webChatService = webChatService;
    this.authTokenService = authTokenService;
    this.objectMapper = objectMapper;
    this.userRepository = userRepository;
  }

  @GetMapping("/session")
  public ApiResponse<WebChatSessionResponse> session(
      @RequestHeader(name = "Authorization", required = false) String authorization) {
    return ApiResponse.ok(webChatService.session(resolveUserId(authorization)));
  }

  @PostMapping("/conversation/reset")
  public ApiResponse<WebChatSessionResponse> reset(
      @RequestHeader(name = "Authorization", required = false) String authorization) {
    return ApiResponse.ok(webChatService.reset(resolveUserId(authorization)));
  }

  @PostMapping("/messages")
  public ApiResponse<WebChatMessageResponse> send(
      @RequestHeader(name = "Authorization", required = false) String authorization,
      @Valid @RequestBody WebChatMessageRequest request) {
    return ApiResponse.ok(webChatService.send(resolveUserId(authorization), request));
  }

  @PostMapping(value = "/messages/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
  public SseEmitter stream(
      @RequestHeader(name = "Authorization", required = false) String authorization,
      @Valid @RequestBody WebChatMessageRequest request) {
    UUID userId = resolveUserId(authorization);
    SseEmitter emitter = new SseEmitter(Duration.ofMinutes(5).toMillis());
    CompletableFuture.runAsync(
        () -> {
          try {
            WebChatMessageResponse result =
                webChatService.stream(
                    userId,
                    request,
                    new WebChatService.StreamSink() {
                      @Override
                      public void delta(String delta) {
                        sendEvent(emitter, "delta", Map.of("delta", delta));
                      }

                      @Override
                      public void replace(String text) {
                        sendEvent(emitter, "replace", Map.of("text", text));
                      }
                    });
            sendEvent(emitter, "done", result);
            emitter.complete();
          } catch (Exception exception) {
            String message =
                exception.getMessage() == null ? exception.getClass().getSimpleName() : exception.getMessage();
            sendEvent(emitter, "error", Map.of("message", message));
            emitter.complete();
          }
        });
    return emitter;
  }

  private UUID resolveUserId(String authorization) {
    String prefix = "Bearer ";
    if (authorization == null || !authorization.startsWith(prefix)) {
      return userRepository
          .findFirstId()
          .orElseThrow(
              () ->
                  new AppException(
                      ErrorCode.UNAUTHORIZED,
                      "No user exists for temporary web chat test access",
                      HttpStatus.UNAUTHORIZED));
    }
    return authTokenService.verifyAndGetUserId(authorization.substring(prefix.length()));
  }

  private void sendEvent(SseEmitter emitter, String event, Object data) {
    try {
      synchronized (emitter) {
        emitter.send(SseEmitter.event().name(event).data(objectMapper.writeValueAsString(data)));
      }
    } catch (Exception exception) {
      throw new IllegalStateException("Unable to stream web chat event", exception);
    }
  }
}
