package com.relay.backend.module.apikey;

import com.relay.backend.common.error.AppException;
import com.relay.backend.common.error.ErrorCode;
import com.relay.backend.module.apikey.dto.ApiKeyResponse;
import com.relay.backend.module.apikey.dto.CreateApiKeyRequest;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

@Service
public class ApiKeyService {

  private static final Base64.Encoder BASE64_URL = Base64.getUrlEncoder().withoutPadding();

  private final ApiKeyRepository apiKeyRepository;
  private final SecureRandom secureRandom = new SecureRandom();

  public ApiKeyService(ApiKeyRepository apiKeyRepository) {
    this.apiKeyRepository = apiKeyRepository;
  }

  public List<ApiKeyResponse> list(UUID userId) {
    return apiKeyRepository.findActiveByUserId(userId).stream()
        .map(record -> toResponse(record, record.keyValue() == null ? displayKey(record.keyHash()) : record.keyValue()))
        .toList();
  }

  public ApiKeyResponse create(UUID userId, CreateApiKeyRequest request) {
    String name = request.name().trim();
    if (apiKeyRepository.existsActiveNameByUserId(userId, name)) {
      throw new AppException(ErrorCode.CONFLICT, "API key name already exists", HttpStatus.CONFLICT);
    }
    String key = issueKey();
    ApiKeyRecord record = apiKeyRepository.create(userId, sha256(key), key, name);
    return toResponse(record, key);
  }

  public void revoke(UUID userId, Long id) {
    if (!apiKeyRepository.revoke(userId, id)) {
      throw new AppException(ErrorCode.NOT_FOUND, "API key not found", HttpStatus.NOT_FOUND);
    }
  }

  public ApiKeyRecord authenticateRawKey(String key) {
    if (key == null || !key.startsWith("relay_")) {
      throw new AppException(ErrorCode.UNAUTHORIZED, "Invalid API key", HttpStatus.UNAUTHORIZED);
    }

    return apiKeyRepository
        .findActiveByHash(sha256(key))
        .orElseThrow(
            () -> new AppException(ErrorCode.UNAUTHORIZED, "Invalid API key", HttpStatus.UNAUTHORIZED));
  }

  private ApiKeyResponse toResponse(ApiKeyRecord record, String key) {
    return new ApiKeyResponse(record.id(), record.name(), key, record.status(), record.createdAt());
  }

  private String issueKey() {
    byte[] bytes = new byte[32];
    secureRandom.nextBytes(bytes);
    return "relay_" + BASE64_URL.encodeToString(bytes);
  }

  private String sha256(String value) {
    try {
      MessageDigest digest = MessageDigest.getInstance("SHA-256");
      return BASE64_URL.encodeToString(digest.digest(value.getBytes(StandardCharsets.UTF_8)));
    } catch (Exception exception) {
      throw new IllegalStateException("Unable to hash API key", exception);
    }
  }

  private String displayKey(String keyHash) {
    return "relay_" + keyHash.substring(0, Math.min(8, keyHash.length())) + "...";
  }
}
