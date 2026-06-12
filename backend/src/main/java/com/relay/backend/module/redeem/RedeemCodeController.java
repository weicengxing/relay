package com.relay.backend.module.redeem;

import com.relay.backend.common.api.ApiResponse;
import com.relay.backend.common.web.ClientIpResolver;
import com.relay.backend.module.auth.AuthTokenService;
import com.relay.backend.module.redeem.dto.RedeemCodeRequest;
import com.relay.backend.module.redeem.dto.RedeemCodeResponse;
import jakarta.servlet.http.HttpServletRequest;
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
  private final ClientIpResolver clientIpResolver;

  public RedeemCodeController(
      RedeemCodeService redeemCodeService,
      AuthTokenService authTokenService,
      ClientIpResolver clientIpResolver) {
    this.redeemCodeService = redeemCodeService;
    this.authTokenService = authTokenService;
    this.clientIpResolver = clientIpResolver;
  }

  @PostMapping("/redeem")
  public ApiResponse<RedeemCodeResponse> redeem(
      @RequestHeader(name = "Authorization", required = false) String authorization,
      @Valid @RequestBody RedeemCodeRequest request,
      HttpServletRequest servletRequest) {
    return ApiResponse.ok(
        redeemCodeService.redeem(
            resolveUserId(authorization), request.code(), clientIpResolver.resolve(servletRequest)));
  }

  private UUID resolveUserId(String authorization) {
    String prefix = "Bearer ";
    if (authorization == null || !authorization.startsWith(prefix)) {
      return authTokenService.verifyAndGetUserId(null);
    }
    return authTokenService.verifyAndGetUserId(authorization.substring(prefix.length()));
  }
}
