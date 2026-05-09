package com.relay.backend.module.webchat.history;

import com.relay.backend.common.api.ApiResponse;
import com.relay.backend.module.auth.AuthTokenService;
import com.relay.backend.module.webchat.history.dto.ChatHistoryDetailResponse;
import com.relay.backend.module.webchat.history.dto.ChatHistoryPageResponse;
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/web-chat/history")
public class ChatHistoryController {

  private final ChatHistoryService chatHistoryService;
  private final AuthTokenService authTokenService;

  public ChatHistoryController(ChatHistoryService chatHistoryService, AuthTokenService authTokenService) {
    this.chatHistoryService = chatHistoryService;
    this.authTokenService = authTokenService;
  }

  @GetMapping
  public ApiResponse<ChatHistoryPageResponse> list(
      @RequestHeader(name = "Authorization", required = false) String authorization,
      @RequestParam(defaultValue = "1") int page,
      @RequestParam(defaultValue = "20") int size) {
    return ApiResponse.ok(chatHistoryService.list(resolveUserId(authorization), page, size));
  }

  @GetMapping("/{id}")
  public ApiResponse<ChatHistoryDetailResponse> detail(
      @RequestHeader(name = "Authorization", required = false) String authorization,
      @PathVariable Long id) {
    return ApiResponse.ok(chatHistoryService.detail(resolveUserId(authorization), id));
  }

  private UUID resolveUserId(String authorization) {
    String prefix = "Bearer ";
    if (authorization == null || !authorization.startsWith(prefix)) {
      return authTokenService.verifyAndGetUserId(null);
    }
    return authTokenService.verifyAndGetUserId(authorization.substring(prefix.length()));
  }
}
