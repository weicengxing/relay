package com.relay.backend.module.webchat.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Size;
import java.util.List;

public record WebChatMessageRequest(
    @Size(max = 20000) String message,
    Boolean newConversation,
    @Size(max = 120) String model,
    @Valid @Size(max = 4) List<ImageAttachment> images) {

  public record ImageAttachment(
      @Size(max = 160) String name,
      @Size(max = 80) String mediaType,
      @Size(max = 16_000_000) String data,
      Long size,
      Integer width,
      Integer height) {}
}
