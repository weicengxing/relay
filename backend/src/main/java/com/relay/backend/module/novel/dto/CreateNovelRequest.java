package com.relay.backend.module.novel.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateNovelRequest(
    @NotBlank @Size(max = 120) String title,
    @Size(max = 80) String author,
    @NotBlank @Size(max = 5000000) String content) {}
