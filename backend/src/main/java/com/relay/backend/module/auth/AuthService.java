package com.relay.backend.module.auth;

import com.relay.backend.common.error.AppException;
import com.relay.backend.common.error.ErrorCode;
import com.relay.backend.module.auth.dto.AuthResponse;
import com.relay.backend.module.auth.dto.LoginRequest;
import com.relay.backend.module.auth.dto.RegisterRequest;
import com.relay.backend.module.user.UserAccount;
import com.relay.backend.module.user.UserRepository;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthService {

  private final UserRepository userRepository;
  private final AuthTokenService authTokenService;

  public AuthService(UserRepository userRepository, AuthTokenService authTokenService) {
    this.userRepository = userRepository;
    this.authTokenService = authTokenService;
  }

  @Transactional
  public AuthResponse register(RegisterRequest request, String registrationIp) {
    UUID userId = UUID.randomUUID();
    String normalizedEmail = request.email().trim().toLowerCase();

    try {
      UserAccount user =
          userRepository.create(userId, normalizedEmail, request.password(), registrationIp, Instant.now());
      return toResponse(user);
    } catch (DuplicateKeyException exception) {
      throw new AppException(
          ErrorCode.CONFLICT, "Email or registration IP has already been used", HttpStatus.CONFLICT);
    }
  }

  public AuthResponse login(LoginRequest request) {
    String normalizedEmail = request.email().trim().toLowerCase();
    UserAccount user =
        userRepository
            .findByEmail(normalizedEmail)
            .orElseThrow(
                () ->
                    new AppException(
                        ErrorCode.INVALID_CREDENTIALS,
                        "Invalid email or password",
                        HttpStatus.UNAUTHORIZED));

    if (!request.password().equals(user.passwordHash())) {
      throw new AppException(
          ErrorCode.INVALID_CREDENTIALS, "Invalid email or password", HttpStatus.UNAUTHORIZED);
    }

    return toResponse(user);
  }

  private AuthResponse toResponse(UserAccount user) {
    return new AuthResponse(
        user.id(),
        user.email(),
        user.balance() == null ? BigDecimal.ZERO : user.balance(),
        authTokenService.issue(user));
  }
}
