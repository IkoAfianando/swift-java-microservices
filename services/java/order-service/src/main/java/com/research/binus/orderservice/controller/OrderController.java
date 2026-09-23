package com.research.binus.orderservice.controller;

import com.research.binus.orderservice.model.*;
import com.research.binus.orderservice.repository.OrderRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.server.ResponseStatusException;

import java.util.*;

@RestController
@RequiredArgsConstructor
public class OrderController {

    private final OrderRepository orderRepository;
    private final RestTemplate restTemplate;

    @Value("${services.product-url}")
    private String productServiceUrl;

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok", "service", "java-order-service", "language", "java");
    }

    @GetMapping("/orders")
    public List<Order> list() {
        return orderRepository.findTop50ByOrderByCreatedAtDesc();
    }

    @PostMapping("/orders")
    public ResponseEntity<Order> create(@RequestBody CreateOrderRequest req) {
        double total = 0;
        List<OrderItem> items = new ArrayList<>();

        for (CreateOrderRequest.ItemRequest ir : req.items()) {
            String url = productServiceUrl + "/products/" + ir.productId();
            try {
                @SuppressWarnings("unchecked")
                Map<String, Object> product = restTemplate.getForObject(url, Map.class);
                double price = ((Number) product.get("price")).doubleValue();
                total += price * ir.quantity();
                items.add(OrderItem.builder()
                        .productId(ir.productId())
                        .quantity(ir.quantity())
                        .unitPrice(price)
                        .build());
            } catch (Exception e) {
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Cannot reach product service");
            }
        }

        Order order = Order.builder()
                .userId(req.userId())
                .total(total)
                .status(OrderStatus.PENDING)
                .build();

        Order saved = orderRepository.save(order);
        for (OrderItem item : items) {
            item.setOrder(saved);
        }
        saved.getItems().addAll(items);
        Order finalOrder = orderRepository.save(saved);

        return ResponseEntity.status(HttpStatus.CREATED).body(finalOrder);
    }

    @GetMapping("/orders/{id}")
    public Order get(@PathVariable UUID id) {
        return orderRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
    }

    @PatchMapping("/orders/{id}/status")
    public Order updateStatus(@PathVariable UUID id, @RequestBody Map<String, String> req) {
        Order order = orderRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        order.setStatus(OrderStatus.valueOf(req.get("status").toUpperCase()));
        return orderRepository.save(order);
    }

    record CreateOrderRequest(UUID userId, List<ItemRequest> items) {
        record ItemRequest(UUID productId, int quantity) {}
    }
}
