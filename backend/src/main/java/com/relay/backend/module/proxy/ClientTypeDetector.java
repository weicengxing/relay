package com.relay.backend.module.proxy;

import jakarta.servlet.http.HttpServletRequest;
import java.nio.charset.StandardCharsets;
import org.springframework.stereotype.Component;

@Component
public class ClientTypeDetector {

  public ClientType detect(HttpServletRequest request, byte[] body) {
    String path = request.getRequestURI();
    if (path.equals("/v1/messages") || path.equals("/v1/messages/count_tokens")) {
      return ClientType.CLAUDE;
    }
    if (path.equals("/v1/responses") || path.equals("/backend-api/codex/responses")) {
      return ClientType.CODEX;
    }

    if (hasHeader(request, "anthropic-version")
        || hasHeader(request, "anthropic-beta")
        || hasHeader(request, "X-Claude-Code-Session-Id")) {
      return ClientType.CLAUDE;
    }
    if (hasHeader(request, "x-codex-installation-id")
        || hasHeader(request, "x-codex-window-id")
        || hasHeader(request, "x-codex-turn-state")) {
      return ClientType.CODEX;
    }

    String text = new String(body, StandardCharsets.UTF_8);
    if (containsJsonField(text, "messages") && containsJsonField(text, "max_tokens") && !containsJsonField(text, "input")) {
      return ClientType.CLAUDE;
    }
    if (containsJsonField(text, "input")
        && (containsJsonField(text, "instructions")
            || containsJsonField(text, "tools")
            || containsJsonField(text, "tool_choice")
            || containsJsonField(text, "reasoning")
            || containsJsonField(text, "prompt_cache_key")
            || containsJsonField(text, "client_metadata"))) {
      return ClientType.CODEX;
    }

    return ClientType.UNKNOWN;
  }

  private boolean hasHeader(HttpServletRequest request, String name) {
    return request.getHeader(name) != null;
  }

  private boolean containsJsonField(String text, String field) {
    return text.contains("\"" + field + "\"");
  }
}
