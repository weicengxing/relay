package com.relay.backend.module.novel.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

public record RateNovelRequest(@Min(1) @Max(5) int score) {}
