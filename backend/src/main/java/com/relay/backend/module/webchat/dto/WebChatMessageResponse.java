package com.relay.backend.module.webchat.dto;

public record WebChatMessageResponse(
    String answer,
    String conversationId,
    String parentMessageId,
    String model,
    Long configId,
    String configName) {}
