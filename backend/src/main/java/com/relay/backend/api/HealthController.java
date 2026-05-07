package com.relay.backend.api;

import com.relay.backend.common.api.ApiResponse;
import java.time.Instant;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class HealthController {

  @GetMapping("/health")
  public ApiResponse<HealthStatus> health() {
    return ApiResponse.ok(new HealthStatus("UP", "relay-backend", Instant.now()));
  }

  @GetMapping("/bootstrap")
  public ApiResponse<BootstrapInfo> bootstrap() {
    return ApiResponse.ok(
        new BootstrapInfo(
            "ready",
            List.of("auth", "user", "billing", "proxy", "admin", "log"),
            List.of(
                "signup",
                "login",
                "balance",
                "api_keys",
                "model_catalog",
                "chat_proxy",
                "request_logs",
                "manual_recharge")));
  }

  public record HealthStatus(String status, String service, Instant timestamp) {}

  public record BootstrapInfo(String status, List<String> modules, List<String> coreFeatures) {}
}
