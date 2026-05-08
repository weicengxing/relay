package com.relay.backend.module.auth;

public interface VerificationMailSender {

  void sendRegisterCode(String email, String code, int ttlMinutes);
}

