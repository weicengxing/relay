package com.relay.backend.module.log;

import com.relay.backend.module.apikey.ApiKeyRecord;
import com.relay.backend.module.proxy.ClientType;
import java.util.List;
import java.util.Map;

public record ProxyRequestLogContext(
    ApiKeyRecord apiKey,
    ClientType clientType,
    String requestMethod,
    String requestUri,
    String queryString,
    String clientIp,
    String userAgent,
    byte[] requestBody,
    byte[] responseBody,
    Map<String, List<String>> responseHeaders,
    int statusCode,
    long useTimeMs,
    long firstTokenMs) {}
