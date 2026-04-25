package com.research.binus.userservice.model;

import java.io.Serializable;
import java.time.LocalDateTime;
import java.util.UUID;

public record UserDTO(UUID id, String name, String email, LocalDateTime createdAt)
        implements Serializable {

    public static UserDTO from(User user) {
        return new UserDTO(user.getId(), user.getName(), user.getEmail(), user.getCreatedAt());
    }
}
