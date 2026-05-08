package com.relay.backend.module.announcement;

import com.relay.backend.common.api.ApiResponse;
import com.relay.backend.module.announcement.dto.AnnouncementInboxResponse;
import com.relay.backend.module.auth.AuthTokenService;
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/announcements")
public class AnnouncementController {

  private final AnnouncementService announcementService;
  private final AuthTokenService authTokenService;

  public AnnouncementController(AnnouncementService announcementService, AuthTokenService authTokenService) {
    this.announcementService = announcementService;
    this.authTokenService = authTokenService;
  }

  @GetMapping
  public ApiResponse<AnnouncementInboxResponse> inbox(
      @RequestHeader(name = "Authorization", required = false) String authorization) {
    return ApiResponse.ok(announcementService.inbox(resolveUserId(authorization)));
  }

  @PostMapping("/read")
  public ApiResponse<AnnouncementInboxResponse> markRead(
      @RequestHeader(name = "Authorization", required = false) String authorization) {
    return ApiResponse.ok(announcementService.markRead(resolveUserId(authorization)));
  }

  private UUID resolveUserId(String authorization) {
    String prefix = "Bearer ";
    if (authorization == null || !authorization.startsWith(prefix)) {
      return authTokenService.verifyAndGetUserId(null);
    }
    return authTokenService.verifyAndGetUserId(authorization.substring(prefix.length()));
  }
}
