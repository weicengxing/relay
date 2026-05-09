package com.relay.backend.module.webchat.history.dto;

public record ChatHistoryImageResponse(
    String name,
    String mediaType,
    Long size,
    Integer width,
    Integer height,
    String data) {}
