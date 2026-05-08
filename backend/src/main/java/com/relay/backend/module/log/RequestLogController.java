package com.relay.backend.module.log;

import com.relay.backend.common.api.ApiResponse;
import com.relay.backend.module.auth.AuthTokenService;
import com.relay.backend.module.log.dto.RequestLogResponse;
import java.util.List;
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/request-logs")
public class RequestLogController {

  private final AuthTokenService authTokenService;
  private final RequestLogService requestLogService;

  public RequestLogController(AuthTokenService authTokenService, RequestLogService requestLogService) {
    this.authTokenService = authTokenService;
    this.requestLogService = requestLogService;
  }

  @GetMapping
  public ApiResponse<List<RequestLogResponse>> list(
      @RequestHeader(name = "Authorization", required = false) String authorization,
      @RequestParam(name = "limit", defaultValue = "100") int limit) {
    UUID userId = resolveUserId(authorization);
    return ApiResponse.ok(requestLogService.list(userId, Math.max(1, Math.min(limit, 200))));
  }

  private UUID resolveUserId(String authorization) {
    String prefix = "Bearer ";
    if (authorization == null || !authorization.startsWith(prefix)) {
      return authTokenService.verifyAndGetUserId(null);
    }
    return authTokenService.verifyAndGetUserId(authorization.substring(prefix.length()));
  }
}
