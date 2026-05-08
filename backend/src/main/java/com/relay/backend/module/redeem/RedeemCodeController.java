package com.relay.backend.module.redeem;

import com.relay.backend.common.api.ApiResponse;
import com.relay.backend.module.auth.AuthTokenService;
import com.relay.backend.module.redeem.dto.RedeemCodeRequest;
import com.relay.backend.module.redeem.dto.RedeemCodeResponse;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/redeem-codes")
public class RedeemCodeController {

  private final RedeemCodeService redeemCodeService;
  private final AuthTokenService authTokenService;

  public RedeemCodeController(RedeemCodeService redeemCodeService, AuthTokenService authTokenService) {
    this.redeemCodeService = redeemCodeService;
    this.authTokenService = authTokenService;
  }

  @PostMapping("/redeem")
  public ApiResponse<RedeemCodeResponse> redeem(
      @RequestHeader(name = "Authorization", required = false) String authorization,
      @Valid @RequestBody RedeemCodeRequest request) {
    return ApiResponse.ok(redeemCodeService.redeem(resolveUserId(authorization), request.code()));
  }

  private UUID resolveUserId(String authorization) {
    String prefix = "Bearer ";
    if (authorization == null || !authorization.startsWith(prefix)) {
      return authTokenService.verifyAndGetUserId(null);
    }
    return authTokenService.verifyAndGetUserId(authorization.substring(prefix.length()));
  }
}
