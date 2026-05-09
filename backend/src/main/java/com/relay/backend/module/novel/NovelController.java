package com.relay.backend.module.novel;

import com.relay.backend.common.api.ApiResponse;
import com.relay.backend.module.auth.AuthTokenService;
import com.relay.backend.module.novel.dto.CreateNovelRequest;
import com.relay.backend.module.novel.dto.NovelPageResponse;
import com.relay.backend.module.novel.dto.NovelResponse;
import com.relay.backend.module.novel.dto.NovelSummaryResponse;
import com.relay.backend.module.novel.dto.RateNovelRequest;
import jakarta.validation.Valid;
import java.util.List;
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/novels")
public class NovelController {

  private final NovelService novelService;
  private final AuthTokenService authTokenService;

  public NovelController(NovelService novelService, AuthTokenService authTokenService) {
    this.novelService = novelService;
    this.authTokenService = authTokenService;
  }

  @GetMapping
  public ApiResponse<NovelPageResponse> list(
      @RequestHeader(name = "Authorization", required = false) String authorization,
      @RequestParam(defaultValue = "1") int page,
      @RequestParam(defaultValue = "20") int size,
      @RequestParam(name = "q", defaultValue = "") String query) {
    return ApiResponse.ok(novelService.list(resolveUserId(authorization), page, size, query));
  }

  @GetMapping("/ranking")
  public ApiResponse<List<NovelSummaryResponse>> ranking(
      @RequestHeader(name = "Authorization", required = false) String authorization,
      @RequestParam(defaultValue = "20") int limit) {
    return ApiResponse.ok(novelService.ranking(resolveUserId(authorization), limit));
  }

  @GetMapping("/{id}")
  public ApiResponse<NovelResponse> detail(
      @RequestHeader(name = "Authorization", required = false) String authorization,
      @PathVariable Long id) {
    return ApiResponse.ok(novelService.detail(resolveUserId(authorization), id));
  }

  @PostMapping
  public ApiResponse<NovelResponse> create(
      @RequestHeader(name = "Authorization", required = false) String authorization,
      @Valid @RequestBody CreateNovelRequest request) {
    return ApiResponse.ok(novelService.create(resolveUserId(authorization), request));
  }

  @PostMapping("/{id}/ratings")
  public ApiResponse<NovelResponse> rate(
      @RequestHeader(name = "Authorization", required = false) String authorization,
      @PathVariable Long id,
      @Valid @RequestBody RateNovelRequest request) {
    return ApiResponse.ok(novelService.rate(resolveUserId(authorization), id, request));
  }

  private UUID resolveUserId(String authorization) {
    String prefix = "Bearer ";
    if (authorization == null || !authorization.startsWith(prefix)) {
      return authTokenService.verifyAndGetUserId(null);
    }
    return authTokenService.verifyAndGetUserId(authorization.substring(prefix.length()));
  }
}
