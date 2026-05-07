package com.relay.backend.module.auth;

import com.relay.backend.common.api.ApiResponse;
import com.relay.backend.common.web.ClientIpResolver;
import com.relay.backend.module.auth.dto.AuthResponse;
import com.relay.backend.module.auth.dto.LoginRequest;
import com.relay.backend.module.auth.dto.RegisterRequest;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/auth")
public class AuthController {

  private final AuthService authService;
  private final ClientIpResolver clientIpResolver;

  public AuthController(AuthService authService, ClientIpResolver clientIpResolver) {
    this.authService = authService;
    this.clientIpResolver = clientIpResolver;
  }

  @PostMapping("/register")
  public ApiResponse<AuthResponse> register(
      @Valid @RequestBody RegisterRequest request, HttpServletRequest httpRequest) {
    return ApiResponse.ok(authService.register(request, clientIpResolver.resolve(httpRequest)));
  }

  @PostMapping("/login")
  public ApiResponse<AuthResponse> login(@Valid @RequestBody LoginRequest request) {
    return ApiResponse.ok(authService.login(request));
  }
}

