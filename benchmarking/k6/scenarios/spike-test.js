/**
 * SPIKE TEST – Sudden burst traffic (flash sale simulation)
 *
 * Scenario: Normal → sudden 10x spike → back to normal
 * Goal: Measure recovery time and how each language handles burst traffic
 * Duration: ~8 minutes
 */

import http from "k6/http";
import { sleep, check, group } from "k6";
import {
  SWIFT, JAVA, jsonHeaders, randomEmail,
  trackedRequest, checkResponse
} from "../helpers/utils.js";

export const options = {
  stages: [
    { duration: "1m",  target: 20  },  // normal baseline
    { duration: "30s", target: 200 },  // sudden spike!
    { duration: "1m",  target: 200 },  // hold the spike
    { duration: "30s", target: 20  },  // drop back
    { duration: "2m",  target: 20  },  // watch recovery
    { duration: "30s", target: 0   },  // ramp down
  ],
  thresholds: {
    "swift_request_duration": ["p(95)<3000"],
    "java_request_duration":  ["p(95)<3000"],
    "http_req_failed":        ["rate<0.20"],  // spike tests may have higher errors
  },
};

export default function () {
  group("Spike – product listing (high read)", function () {
    const swiftRes = trackedRequest("swift", http.get(`${SWIFT.PRODUCT}/products`));
    const javaRes  = trackedRequest("java",  http.get(`${JAVA.PRODUCT}/products`));
    checkResponse(swiftRes, "Swift spike /products");
    checkResponse(javaRes,  "Java spike /products");
  });

  sleep(0.2);

  group("Spike – health check (should always pass)", function () {
    const swiftHealth = http.get(`${SWIFT.USER}/health`);
    const javaHealth  = http.get(`${JAVA.USER}/actuator/health`);

    check(swiftHealth, { "Swift health UP": (r) => r.status === 200 });
    check(javaHealth,  { "Java health UP":  (r) => r.status === 200 });
  });
}
