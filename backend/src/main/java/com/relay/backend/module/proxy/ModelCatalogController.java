package com.relay.backend.module.proxy;

import com.relay.backend.common.api.ApiResponse;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/models")
public class ModelCatalogController {

  private final ModelCatalogRepository modelCatalogRepository;

  public ModelCatalogController(ModelCatalogRepository modelCatalogRepository) {
    this.modelCatalogRepository = modelCatalogRepository;
  }

  @GetMapping
  public ApiResponse<List<ModelCatalogItem>> list() {
    return ApiResponse.ok(modelCatalogRepository.findEnabled());
  }
}
