package com.relay.backend.common.web;

import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class ClientIpResolver {

  private static final List<String> FORWARDED_HEADERS =
      List.of("CF-Connecting-IP", "X-Forwarded-For", "X-Real-IP");

  public String resolve(HttpServletRequest request) {
    for (String header : FORWARDED_HEADERS) {
      String value = request.getHeader(header);
      if (value != null && !value.isBlank()) {
        return value.split(",")[0].trim();
      }
    }

    return request.getRemoteAddr();
  }
}

