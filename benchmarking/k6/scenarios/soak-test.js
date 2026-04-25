/**
 * SOAK TEST – Long duration endurance test
 *
 * Scenario: Steady moderate load for 2 hours
 * Goal: Detect memory leaks, connection pool exhaustion, GC pressure over time
 * Key research question: Does Swift's memory usage grow over time vs Java?
 * Duration: 2 hours (adjust SOAK_DURATION env var)
 */

import http from "k6/http";
import { sleep, check, group } from "k6";
import {
  SWIFT, JAVA, jsonHeaders, randomEmail,
  trackedRequest, checkResponse
} from "../helpers/utils.js";

const SOAK_DURATION = __ENV.SOAK_DURATION || "2h";
const SOAK_VUS      = parseInt(__ENV.SOAK_VUS || "30");

export const options = {
  stages: [
    { duration: "5m",          target: SOAK_VUS },  // ramp up
    { duration: SOAK_DURATION, target: SOAK_VUS },  // hold steady
    { duration: "5m",          target: 0         },  // ramp down
  ],
  thresholds: {
    "swift_request_duration": ["p(95)<1000"],
    "java_request_duration":  ["p(95)<1000"],
    "swift_error_rate":       ["rate<0.005"],
    "java_error_rate":        ["rate<0.005"],
    "http_req_failed":        ["rate<0.01"],
  },
};

let requestCount = 0;

export default function () {
  requestCount++;

  // Mix of reads and writes (80/20 read-write ratio)
  if (requestCount % 5 === 0) {
    // Write operation (20%)
    group("Soak – POST /users", function () {
      const body = JSON.stringify({ name: "SoakUser", email: randomEmail(), password: "Soak123!" });
      trackedRequest("swift", http.post(`${SWIFT.USER}/users`, body, { headers: jsonHeaders() }));
      trackedRequest("java",  http.post(`${JAVA.USER}/users`,  body, { headers: jsonHeaders() }));
    });
  } else {
    // Read operations (80%)
    group("Soak – GET /products", function () {
      trackedRequest("swift", http.get(`${SWIFT.PRODUCT}/products`));
      trackedRequest("java",  http.get(`${JAVA.PRODUCT}/products`));
    });

    group("Soak – GET /users", function () {
      trackedRequest("swift", http.get(`${SWIFT.USER}/users`));
      trackedRequest("java",  http.get(`${JAVA.USER}/users`));
    });
  }

  // Log memory observations periodically
  if (requestCount % 1000 === 0) {
    console.log(`[Soak] Iteration ${requestCount} complete – check Grafana memory panels`);
  }

  sleep(2);  // 2 second think time to simulate realistic users
}
