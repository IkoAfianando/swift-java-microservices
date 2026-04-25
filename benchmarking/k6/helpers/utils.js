import { check, sleep } from "k6";
import http from "k6/http";
import { Trend, Counter, Rate, Gauge } from "k6/metrics";

// ──────────────────────────────────────────────────────────
// Custom metrics for research comparison
// ──────────────────────────────────────────────────────────

export const swiftLatency = new Trend("swift_request_duration", true);
export const javaLatency  = new Trend("java_request_duration", true);
export const swiftErrors  = new Rate("swift_error_rate");
export const javaErrors   = new Rate("java_error_rate");
export const swiftRPS     = new Counter("swift_requests_total");
export const javaRPS      = new Counter("java_requests_total");

// ──────────────────────────────────────────────────────────
// Service base URLs
// ──────────────────────────────────────────────────────────

export const SWIFT = {
  USER:    __ENV.SWIFT_USER_URL    || "http://localhost:8081",
  PRODUCT: __ENV.SWIFT_PRODUCT_URL || "http://localhost:8082",
  ORDER:   __ENV.SWIFT_ORDER_URL   || "http://localhost:8083",
};

export const JAVA = {
  USER:    __ENV.JAVA_USER_URL    || "http://localhost:9081",
  PRODUCT: __ENV.JAVA_PRODUCT_URL || "http://localhost:9082",
  ORDER:   __ENV.JAVA_ORDER_URL   || "http://localhost:9083",
};

// ──────────────────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────────────────

export function jsonHeaders() {
  return { "Content-Type": "application/json", "Accept": "application/json" };
}

export function randomItem(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

export function randomInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

export function randomEmail() {
  // __VU/__ITER are undefined in setup()/teardown(), guard with typeof.
  const vu = typeof __VU !== "undefined" ? __VU : "s";
  const it = typeof __ITER !== "undefined" ? __ITER : 0;
  return `user_vu${vu}_it${it}_${Date.now()}_${randomInt(100000, 999999)}@test.com`;
}

// Track request metrics and record to custom trends
export function trackedRequest(lang, res) {
  if (lang === "swift") {
    swiftLatency.add(res.timings.duration);
    swiftErrors.add(res.status >= 400);
    swiftRPS.add(1);
  } else {
    javaLatency.add(res.timings.duration);
    javaErrors.add(res.status >= 400);
    javaRPS.add(1);
  }
  return res;
}

// Standard check suite for any HTTP response
export function checkResponse(res, name) {
  return check(res, {
    [`${name}: status 2xx`]: (r) => r.status >= 200 && r.status < 300,
    [`${name}: response time < 2s`]: (r) => r.timings.duration < 2000,
    [`${name}: has body`]: (r) => r.body && r.body.length > 0,
  });
}

// Compare two responses and log difference
export function compareResponses(swiftRes, javaRes, endpoint) {
  const diff = swiftRes.timings.duration - javaRes.timings.duration;
  const winner = diff < 0 ? "Swift" : "Java";
  console.log(
    `[${endpoint}] Swift: ${swiftRes.timings.duration.toFixed(1)}ms | Java: ${javaRes.timings.duration.toFixed(1)}ms | Winner: ${winner} by ${Math.abs(diff).toFixed(1)}ms`
  );
}
