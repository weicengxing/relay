package com.relay.backend.config;

import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class MailConfig {

  @Bean
  public JavaMailSender javaMailSender(AppProperties appProperties) {
    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    sender.setHost(appProperties.getMail().getHost());
    sender.setPort(appProperties.getMail().getPort());
    sender.setUsername(appProperties.getMail().getUsername());
    sender.setPassword(appProperties.getMail().getPassword());

    Properties properties = sender.getJavaMailProperties();
    properties.put("mail.smtp.auth", "true");
    properties.put("mail.smtp.ssl.enable", "true");
    properties.put("mail.smtp.starttls.enable", "false");
    properties.put("mail.smtp.timeout", "10000");
    properties.put("mail.smtp.connectiontimeout", "10000");
    return sender;
  }
}
