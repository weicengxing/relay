package com.relay.backend.module.log;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.relay.backend.module.apikey.ApiKeyRecord;
import com.relay.backend.module.proxy.ClientType;
import com.relay.backend.module.proxy.ModelCatalogItem;
import com.relay.backend.module.proxy.ModelCatalogRepository;
import com.relay.backend.module.user.BalanceUpdatePublisher;
import com.relay.backend.module.user.UserRepository;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import tools.jackson.databind.ObjectMapper;

class RequestLogServiceTests {

  @Test
  void parsesResponsesCompletedUsageFromSse() {
    RequestLogRepository requestLogRepository = mock(RequestLogRepository.class);
    ModelCatalogRepository modelCatalogRepository = mock(ModelCatalogRepository.class);
    UserRepository userRepository = mock(UserRepository.class);
    BalanceUpdatePublisher balanceUpdatePublisher = mock(BalanceUpdatePublisher.class);
    BillingSettingsRepository billingSettingsRepository = mock(BillingSettingsRepository.class);
    when(billingSettingsRepository.costMultiplier()).thenReturn(new BigDecimal("1.2"));
    when(userRepository.deductBalance(
            UUID.fromString("00000000-0000-0000-0000-000000000001"), new BigDecimal("0.007769")))
        .thenReturn(new BigDecimal("4.992231"));
    when(modelCatalogRepository.findById("gpt-5.4"))
        .thenReturn(
            Optional.of(
                new ModelCatalogItem(
                    "gpt-5.4",
                    "GPT 5.4",
                    "OpenAI",
                    new BigDecimal("1.00"),
                    new BigDecimal("10.00"),
                    new BigDecimal("0.25"),
                    new BigDecimal("1.00"),
                    List.of())));
    RequestLogService service =
        new RequestLogService(
            requestLogRepository,
            modelCatalogRepository,
            userRepository,
            balanceUpdatePublisher,
            billingSettingsRepository,
            new ObjectMapper());

    String response =
        """
        : relay-keepalive

        data: {"type":"response.created","response":{"id":"resp_test","model":"gpt-5.4"}}

        data: {"type":"response.completed","response":{"id":"resp_test","model":"gpt-5.4","usage":{"input_tokens":12000,"input_tokens_details":{"cached_tokens":11648},"output_tokens":321,"output_tokens_details":{"reasoning_tokens":12},"total_tokens":12321}}}

        data: [DONE]

        """;

    service.recordProxyRequestAsync(
        new ProxyRequestLogContext(
            new ApiKeyRecord(
                UUID.fromString("00000000-0000-0000-0000-000000000001"),
                10L,
                "abcdef1234567890",
                "relay_test",
                "mykey",
                "active",
                Instant.parse("2026-05-08T00:00:00Z")),
            ClientType.CODEX,
            "POST",
            "/v1/responses",
            null,
            "127.0.0.1",
            "codex",
            "{\"model\":\"gpt-5.4\"}".getBytes(java.nio.charset.StandardCharsets.UTF_8),
            response.getBytes(java.nio.charset.StandardCharsets.UTF_8),
            4L,
            Map.of(),
            200,
            3900L,
            20L));

    ArgumentCaptor<RequestLogRecord> captor = ArgumentCaptor.forClass(RequestLogRecord.class);
    verify(requestLogRepository).save(captor.capture());
    RequestLogRecord saved = captor.getValue();

    assertThat(saved.model()).isEqualTo("gpt-5.4");
    assertThat(saved.promptTokens()).isEqualTo(12000);
    assertThat(saved.completionTokens()).isEqualTo(321);
    assertThat(saved.cacheReadTokens()).isEqualTo(11648);
    assertThat(saved.cost()).isEqualByComparingTo("0.007769");
    verify(userRepository)
        .deductBalance(
            UUID.fromString("00000000-0000-0000-0000-000000000001"), new BigDecimal("0.007769"));
    verify(balanceUpdatePublisher)
        .publish(UUID.fromString("00000000-0000-0000-0000-000000000001"), new BigDecimal("4.992231"));
  }
}
