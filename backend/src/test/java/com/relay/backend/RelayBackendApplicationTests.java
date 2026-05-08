package com.relay.backend;

import com.relay.backend.test.RedisTestConfig;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

@SpringBootTest
@Import(RedisTestConfig.class)
class RelayBackendApplicationTests {

  @Test
  void contextLoads() {}
}
