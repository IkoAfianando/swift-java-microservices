package com.research.binus.userservice.controller;

import com.research.binus.userservice.model.User;
import com.research.binus.userservice.model.UserDTO;
import com.research.binus.userservice.repository.UserRepository;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.RequiredArgsConstructor;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/users")
@RequiredArgsConstructor
public class UserController {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;

    // GET /users
    @GetMapping
    @Cacheable(value = "users-list")
    public List<UserDTO> list() {
        return userRepository.findAll().stream().map(UserDTO::from).toList();
    }

    // POST /users
    @PostMapping
    @CacheEvict(value = "users-list", allEntries = true)
    public ResponseEntity<UserDTO> create(@Valid @RequestBody CreateUserRequest req) {
        if (userRepository.existsByEmail(req.email())) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Email already registered");
        }
        User user = User.builder()
                .name(req.name())
                .email(req.email())
                .passwordHash(passwordEncoder.encode(req.password()))
                .build();
        User saved = userRepository.save(user);
        return ResponseEntity.status(HttpStatus.CREATED).body(UserDTO.from(saved));
    }

    // GET /users/:id
    @GetMapping("/{id}")
    @Cacheable(value = "user", key = "#id")
    public UserDTO get(@PathVariable UUID id) {
        return userRepository.findById(id)
                .map(UserDTO::from)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "User not found"));
    }

    // PUT /users/:id
    @PutMapping("/{id}")
    @CacheEvict(value = {"user", "users-list"}, key = "#id", allEntries = true)
    public UserDTO update(@PathVariable UUID id, @Valid @RequestBody CreateUserRequest req) {
        User user = userRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        user.setName(req.name());
        user.setEmail(req.email());
        return UserDTO.from(userRepository.save(user));
    }

    // DELETE /users/:id
    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    @CacheEvict(value = {"user", "users-list"}, allEntries = true)
    public void delete(@PathVariable UUID id) {
        if (!userRepository.existsById(id)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        userRepository.deleteById(id);
    }

    // POST /auth/login
    @PostMapping("/login")
    public ResponseEntity<Map<String, Object>> login(@RequestBody LoginRequest req) {
        User user = userRepository.findByEmail(req.email())
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Invalid credentials"));
        if (!passwordEncoder.matches(req.password(), user.getPasswordHash())) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Invalid credentials");
        }
        // Simple token (use JWT in production)
        String token = UUID.randomUUID().toString().replace("-", "");
        return ResponseEntity.ok(Map.of("token", token, "user", UserDTO.from(user)));
    }

    // ──────────────────────────────────────────────────────
    // Request DTOs
    // ──────────────────────────────────────────────────────

    record CreateUserRequest(
            @NotBlank @Size(min = 2, max = 100) String name,
            @NotBlank @Email String email,
            @NotBlank @Size(min = 8) String password
    ) {}

    record LoginRequest(String email, String password) {}
}
