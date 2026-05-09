package com.relay.backend.module.webchat.history.dto;

import java.util.List;

public record ChatHistoryDetailResponse(
    ChatHistoryFileResponse file,
    List<ChatHistoryTurnResponse> turns) {}
