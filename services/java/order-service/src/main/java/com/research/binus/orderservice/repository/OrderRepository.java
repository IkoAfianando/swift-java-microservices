package com.research.binus.orderservice.repository;

import com.research.binus.orderservice.model.Order;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface OrderRepository extends JpaRepository<Order, UUID> {

    // Matches the Vapor service, which returns the 50 most recent orders.
    List<Order> findTop50ByOrderByCreatedAtDesc();
}
