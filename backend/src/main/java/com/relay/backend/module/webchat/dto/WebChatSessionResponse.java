package com.relay.backend.module.webchat.dto;

public record WebChatSessionResponse(
    Long configId,
    String configName,
    String model,
    String conversationId,
    boolean hasConversation) {}
