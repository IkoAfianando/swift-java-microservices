package com.research.binus.productservice.controller;

import com.research.binus.productservice.model.Product;
import com.research.binus.productservice.repository.ProductRepository;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.cache.annotation.*;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping
@RequiredArgsConstructor
public class ProductController {

    private final ProductRepository productRepository;

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok", "service", "java-product-service", "language", "java");
    }

    @GetMapping("/products")
    @Cacheable("products-list")
    public List<Product> list() {
        return productRepository.findAll();
    }

    @PostMapping("/products")
    @CacheEvict(value = "products-list", allEntries = true)
    public ResponseEntity<Product> create(@Valid @RequestBody Product product) {
        return ResponseEntity.status(HttpStatus.CREATED).body(productRepository.save(product));
    }

    @GetMapping("/products/{id}")
    @Cacheable(value = "product", key = "#id")
    public Product get(@PathVariable UUID id) {
        return productRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
    }

    @PutMapping("/products/{id}")
    @CacheEvict(value = {"product", "products-list"}, allEntries = true)
    public Product update(@PathVariable UUID id, @Valid @RequestBody Product req) {
        Product p = productRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        p.setName(req.getName());
        p.setDescription(req.getDescription());
        p.setPrice(req.getPrice());
        p.setStock(req.getStock());
        return productRepository.save(p);
    }

    @DeleteMapping("/products/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    @CacheEvict(value = {"product", "products-list"}, allEntries = true)
    public void delete(@PathVariable UUID id) {
        if (!productRepository.existsById(id)) throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        productRepository.deleteById(id);
    }
}
