package com.relay.backend.module.user;

import com.relay.backend.common.api.ApiResponse;
import com.relay.backend.common.error.AppException;
import com.relay.backend.common.error.ErrorCode;
import com.relay.backend.module.auth.AuthTokenService;
import com.relay.backend.module.user.dto.BalanceResponse;
import java.math.BigDecimal;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequestMapping("/api/balance")
public class UserController {

  private final AuthTokenService authTokenService;
  private final UserRepository userRepository;
  private final BalanceUpdatePublisher balanceUpdatePublisher;

  public UserController(
      AuthTokenService authTokenService,
      UserRepository userRepository,
      BalanceUpdatePublisher balanceUpdatePublisher) {
    this.authTokenService = authTokenService;
    this.userRepository = userRepository;
    this.balanceUpdatePublisher = balanceUpdatePublisher;
  }

  @GetMapping
  public ApiResponse<BalanceResponse> current(
      @RequestHeader(name = "Authorization", required = false) String authorization) {
    return ApiResponse.ok(new BalanceResponse(currentBalance(resolveUserId(authorization))));
  }

  @GetMapping(value = "/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
  public SseEmitter stream(@RequestHeader(name = "Authorization", required = false) String authorization) {
    UUID userId = resolveUserId(authorization);
    return balanceUpdatePublisher.subscribe(userId, currentBalance(userId));
  }

  private BigDecimal currentBalance(UUID userId) {
    return userRepository
        .findById(userId)
        .map(user -> user.balance() == null ? BigDecimal.ZERO : user.balance())
        .orElseThrow(() -> new AppException(ErrorCode.UNAUTHORIZED, "Unauthorized", HttpStatus.UNAUTHORIZED));
  }

  private UUID resolveUserId(String authorization) {
    String prefix = "Bearer ";
    if (authorization == null || !authorization.startsWith(prefix)) {
      return authTokenService.verifyAndGetUserId(null);
    }
    return authTokenService.verifyAndGetUserId(authorization.substring(prefix.length()));
  }
}
