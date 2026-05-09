package com.relay.backend.module.webchat.history.dto;

import java.time.Instant;
import java.util.List;

public record ChatHistoryTurnResponse(
    Instant createdAt,
    String conversationId,
    String parentMessageId,
    String model,
    String configName,
    String userMessage,
    List<ChatHistoryImageResponse> images,
    String assistantAnswer) {}
