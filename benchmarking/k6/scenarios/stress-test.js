/**
 * STRESS TEST – Push services to their breaking point
 *
 * Scenario: Ramp up beyond normal capacity to find the breaking point
 * Goal: Identify max throughput before error rate spikes
 * Duration: ~15 minutes
 */

import http from "k6/http";
import { sleep, check, group } from "k6";
import {
  SWIFT, JAVA, jsonHeaders, randomEmail,
  trackedRequest, checkResponse
} from "../helpers/utils.js";

export const options = {
  stages: [
    { duration: "2m",  target: 50   },  // baseline
    { duration: "3m",  target: 200  },  // moderate load
    { duration: "3m",  target: 500  },  // high load
    { duration: "3m",  target: 1000 },  // extreme load
    { duration: "2m",  target: 0    },  // recovery
  ],
  thresholds: {
    // Stress test: more lenient thresholds – we want to see where it breaks
    "swift_request_duration": ["p(95)<2000"],
    "java_request_duration":  ["p(95)<2000"],
    "http_req_failed":        ["rate<0.10"],  // allow up to 10% errors
  },
};

export default function () {
  group("Stress – GET /users (read-heavy)", function () {
    const swiftRes = trackedRequest("swift", http.get(`${SWIFT.USER}/users`));
    const javaRes  = trackedRequest("java",  http.get(`${JAVA.USER}/users`));
    checkResponse(swiftRes, "Swift stress GET /users");
    checkResponse(javaRes,  "Java stress GET /users");
  });

  sleep(0.1);  // minimal sleep to push max concurrency

  group("Stress – POST /users (write-heavy)", function () {
    const body = JSON.stringify({ name: "StressUser", email: randomEmail(), password: "Stress123!" });
    trackedRequest("swift", http.post(`${SWIFT.USER}/users`, body, { headers: jsonHeaders() }));
    trackedRequest("java",  http.post(`${JAVA.USER}/users`,  body, { headers: jsonHeaders() }));
  });

  sleep(0.1);

  group("Stress – GET /products (DB read)", function () {
    trackedRequest("swift", http.get(`${SWIFT.PRODUCT}/products`));
    trackedRequest("java",  http.get(`${JAVA.PRODUCT}/products`));
  });
}
