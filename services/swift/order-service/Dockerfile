# ── Build stage ──────────────────────────────────────────
FROM swift:6.0-jammy AS builder

WORKDIR /build

COPY Package.swift ./
RUN swift package resolve

COPY Sources/ Sources/

RUN swift build -c release --product App 2>&1

# ── Runtime stage ─────────────────────────────────────────
FROM ubuntu:22.04 AS runtime

RUN apt-get update && apt-get install -y \
    libatomic1 libbsd0 libcurl4 libxml2 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /usr/lib/swift/linux/ /usr/lib/swift/linux/
COPY --from=builder /build/.build/release/App ./App

RUN useradd -r -s /bin/false appuser && chown appuser /app/App
USER appuser

ENV PORT=8083
EXPOSE 8083

HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

CMD ["./App", "serve", "--env", "production", "--hostname", "0.0.0.0"]
