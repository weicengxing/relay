package com.relay.backend.module.proxy;

import java.math.BigDecimal;
import java.util.List;

public record ModelCatalogItem(
    String id,
    String name,
    String provider,
    BigDecimal inputPrice,
    BigDecimal outputPrice,
    BigDecimal cachedInputPrice,
    BigDecimal cacheCreationPrice,
    List<String> tags) {}
