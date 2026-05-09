package com.relay.backend.module.user;

import com.relay.backend.module.user.dto.BalanceResponse;
import java.io.IOException;
import java.math.BigDecimal;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@Service
public class BalanceUpdatePublisher {

  private final ConcurrentHashMap<UUID, Set<SseEmitter>> emitters = new ConcurrentHashMap<>();

  public SseEmitter subscribe(UUID userId, BigDecimal currentBalance) {
    SseEmitter emitter = new SseEmitter(0L);
    emitters.computeIfAbsent(userId, ignored -> ConcurrentHashMap.newKeySet()).add(emitter);

    Runnable cleanup = () -> remove(userId, emitter);
    emitter.onCompletion(cleanup);
    emitter.onTimeout(cleanup);
    emitter.onError(ignored -> cleanup.run());

    send(userId, emitter, currentBalance);
    return emitter;
  }

  public void publish(UUID userId, BigDecimal balance) {
    Set<SseEmitter> userEmitters = emitters.get(userId);
    if (userEmitters == null || userEmitters.isEmpty()) {
      return;
    }

    for (SseEmitter emitter : userEmitters) {
      send(userId, emitter, balance);
    }
  }

  private void send(UUID userId, SseEmitter emitter, BigDecimal balance) {
    try {
      emitter.send(SseEmitter.event().name("balance").data(new BalanceResponse(safeBalance(balance))));
    } catch (IOException | IllegalStateException exception) {
      remove(userId, emitter);
      emitter.complete();
    }
  }

  private BigDecimal safeBalance(BigDecimal balance) {
    return balance == null ? BigDecimal.ZERO : balance;
  }

  private void remove(UUID userId, SseEmitter emitter) {
    Set<SseEmitter> userEmitters = emitters.get(userId);
    if (userEmitters == null) {
      return;
    }
    userEmitters.remove(emitter);
    if (userEmitters.isEmpty()) {
      emitters.remove(userId, userEmitters);
    }
  }
}
