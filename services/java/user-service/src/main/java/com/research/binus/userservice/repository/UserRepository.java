package com.research.binus.userservice.repository;

import com.research.binus.userservice.model.User;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface UserRepository extends JpaRepository<User, UUID> {
    Optional<User> findByEmail(String email);
    boolean existsByEmail(String email);

    // Row cap and ordering are part of the parity contract: the Vapor service
    // answers GET /users with the 100 most recent rows, so the Spring service
    // must return the same result set rather than the whole table. Leaving this
    // unbounded makes the response grow with every write during a run and turns
    // a serialisation cost into what looks like a framework difference.
    List<User> findTop100ByOrderByCreatedAtDesc();
}
