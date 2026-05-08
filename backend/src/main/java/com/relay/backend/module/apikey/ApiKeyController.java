package com.relay.backend.module.apikey;

import com.relay.backend.common.api.ApiResponse;
import com.relay.backend.module.apikey.dto.ApiKeyResponse;
import com.relay.backend.module.apikey.dto.CreateApiKeyRequest;
import com.relay.backend.module.auth.AuthTokenService;
import jakarta.validation.Valid;
import java.util.List;
import java.util.UUID;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/api-keys")
public class ApiKeyController {

  private final ApiKeyService apiKeyService;
  private final AuthTokenService authTokenService;

  public ApiKeyController(ApiKeyService apiKeyService, AuthTokenService authTokenService) {
    this.apiKeyService = apiKeyService;
    this.authTokenService = authTokenService;
  }

  @GetMapping
  public ApiResponse<List<ApiKeyResponse>> list(
      @RequestHeader(name = "Authorization", required = false) String authorization) {
    return ApiResponse.ok(apiKeyService.list(resolveUserId(authorization)));
  }

  @PostMapping
  public ApiResponse<ApiKeyResponse> create(
      @RequestHeader(name = "Authorization", required = false) String authorization,
      @Valid @RequestBody CreateApiKeyRequest request) {
    return ApiResponse.ok(apiKeyService.create(resolveUserId(authorization), request));
  }

  @DeleteMapping("/{id}")
  public ApiResponse<Void> revoke(
      @RequestHeader(name = "Authorization", required = false) String authorization,
      @PathVariable Long id) {
    apiKeyService.revoke(resolveUserId(authorization), id);
    return ApiResponse.ok();
  }

  private UUID resolveUserId(String authorization) {
    String prefix = "Bearer ";
    if (authorization == null || !authorization.startsWith(prefix)) {
      return authTokenService.verifyAndGetUserId(null);
    }
    return authTokenService.verifyAndGetUserId(authorization.substring(prefix.length()));
  }
}
