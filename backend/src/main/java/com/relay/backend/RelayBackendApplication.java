package com.relay.backend;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class RelayBackendApplication {

  public static void main(String[] args) {
    SpringApplication.run(RelayBackendApplication.class, args);
  }
}
