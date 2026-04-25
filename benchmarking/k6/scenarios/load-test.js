/**
 * LOAD TEST – Simulate realistic production load
 *
 * Scenario: Gradual ramp-up to steady state
 * Goal: Compare throughput & latency of Swift vs Java under normal load
 * Duration: ~10 minutes
 */

import http from "k6/http";
import { sleep, check, group } from "k6";
import {
  SWIFT, JAVA, jsonHeaders, randomEmail, randomInt,
  trackedRequest, checkResponse, compareResponses
} from "../helpers/utils.js";

export const options = {
  stages: [
    { duration: "1m",  target: 10  },  // warm-up
    { duration: "3m",  target: 50  },  // ramp up
    { duration: "3m",  target: 100 },  // steady state
    { duration: "2m",  target: 50  },  // scale down
    { duration: "1m",  target: 0   },  // cool down
  ],
  thresholds: {
    // Both languages should meet these thresholds
    "swift_request_duration": ["p(95)<500", "p(99)<1000"],
    "java_request_duration":  ["p(95)<500", "p(99)<1000"],
    "swift_error_rate":       ["rate<0.01"],
    "java_error_rate":        ["rate<0.01"],
    "http_req_duration":      ["p(95)<2000"],
  },
  ext: {
    loadimpact: {
      projectID: 0,
      name: "Swift vs Java – Load Test",
    },
  },
};

// Seed data: created during setup
let userIds = [];
let productIds = [];

export function setup() {
  // Create test users in both languages
  for (let i = 0; i < 5; i++) {
    const body = JSON.stringify({ name: `TestUser${i}`, email: randomEmail(), password: "Test1234!" });
    const swiftRes = http.post(`${SWIFT.USER}/users`, body, { headers: jsonHeaders() });
    const javaRes  = http.post(`${JAVA.USER}/users`,  body, { headers: jsonHeaders() });
    if (swiftRes.status === 201) {
      const data = JSON.parse(swiftRes.body);
      if (data.id) userIds.push({ swiftId: data.id });
    }
    if (javaRes.status === 201) {
      const data = JSON.parse(javaRes.body);
      if (data.id) {
        if (userIds[i]) userIds[i].javaId = data.id;
        else userIds.push({ javaId: data.id });
      }
    }

    // Create test products
    const prod = JSON.stringify({ name: `Product${i}`, price: randomInt(10, 500), stock: 100 });
    const sRes = http.post(`${SWIFT.PRODUCT}/products`, prod, { headers: jsonHeaders() });
    const jRes = http.post(`${JAVA.PRODUCT}/products`,  prod, { headers: jsonHeaders() });
    if (sRes.status === 201) {
      const d = JSON.parse(sRes.body);
      productIds.push({ swiftId: d.id });
    }
    if (jRes.status === 201) {
      const d = JSON.parse(jRes.body);
      if (productIds[i]) productIds[i].javaId = d.id;
      else productIds.push({ javaId: d.id });
    }
  }

  console.log(`Setup complete: ${userIds.length} users, ${productIds.length} products created`);
  return { userIds, productIds };
}

export default function (data) {
  const { userIds, productIds } = data;

  group("GET /users – list users", function () {
    const swiftRes = trackedRequest("swift", http.get(`${SWIFT.USER}/users`));
    const javaRes  = trackedRequest("java",  http.get(`${JAVA.USER}/users`));
    checkResponse(swiftRes, "Swift GET /users");
    checkResponse(javaRes,  "Java GET /users");
    compareResponses(swiftRes, javaRes, "GET /users");
  });

  sleep(0.5);

  group("GET /products – list products", function () {
    const swiftRes = trackedRequest("swift", http.get(`${SWIFT.PRODUCT}/products`));
    const javaRes  = trackedRequest("java",  http.get(`${JAVA.PRODUCT}/products`));
    checkResponse(swiftRes, "Swift GET /products");
    checkResponse(javaRes,  "Java GET /products");
    compareResponses(swiftRes, javaRes, "GET /products");
  });

  sleep(0.5);

  group("POST /users – create user", function () {
    const body = JSON.stringify({ name: `LoadUser`, email: randomEmail(), password: "Test1234!" });
    const swiftRes = trackedRequest("swift", http.post(`${SWIFT.USER}/users`, body, { headers: jsonHeaders() }));
    const javaRes  = trackedRequest("java",  http.post(`${JAVA.USER}/users`,  body, { headers: jsonHeaders() }));
    checkResponse(swiftRes, "Swift POST /users");
    checkResponse(javaRes,  "Java POST /users");
  });

  sleep(0.5);

  group("POST /orders – create order", function () {
    if (userIds.length === 0 || productIds.length === 0) return;
    const uid = userIds[randomInt(0, userIds.length - 1)];
    const pid = productIds[randomInt(0, productIds.length - 1)];

    if (uid.swiftId && pid.swiftId) {
      const swiftBody = JSON.stringify({ userId: uid.swiftId, items: [{ productId: pid.swiftId, quantity: 1 }] });
      const swiftRes  = trackedRequest("swift", http.post(`${SWIFT.ORDER}/orders`, swiftBody, { headers: jsonHeaders() }));
      checkResponse(swiftRes, "Swift POST /orders");
    }

    if (uid.javaId && pid.javaId) {
      const javaBody = JSON.stringify({ userId: uid.javaId, items: [{ productId: pid.javaId, quantity: 1 }] });
      const javaRes  = trackedRequest("java", http.post(`${JAVA.ORDER}/orders`, javaBody, { headers: jsonHeaders() }));
      checkResponse(javaRes, "Java POST /orders");
    }
  });

  sleep(randomInt(1, 3));
}

export function teardown(data) {
  console.log("Load test complete. Check Grafana for metrics.");
}
