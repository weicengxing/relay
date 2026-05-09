package com.relay.backend.module.webchat;

import java.time.Instant;
import java.util.UUID;

public record WebChatSession(
    UUID userId,
    Long configId,
    String conversationId,
    String parentMessageId,
    Instant updatedAt,
    WebChatModelConfig config) {}
