package com.relay.backend.module.novel;

import java.util.UUID;

public interface NovelStorageService {

  NovelStorageObject save(UUID userId, String title, String content);

  String read(String objectKey);
}
