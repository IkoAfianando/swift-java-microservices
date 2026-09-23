/**
 * Revision 3 benchmark driver, one stack under test per run.
 *
 * The original scripts drove Swift and Java inside the same virtual-user
 * iteration. That kept external conditions identical but made the two stacks
 * compete for the same host CPU, which is exactly what the reviewers objected
 * to. Here a run targets a single stack, so the system under test owns its
 * whole CPU quota while it is measured.
 *
 * Environment:
 *   TARGET    swift | java
 *   SCENARIO  load | stress | spike | soak
 *   USER_URL, PRODUCT_URL, ORDER_URL
 */

import http from "k6/http";
import { sleep, group } from "k6";
import { Trend, Rate, Counter } from "k6/metrics";

const TARGET   = __ENV.TARGET   || "swift";
const SCENARIO = __ENV.SCENARIO || "load";

const USER    = __ENV.USER_URL    || (TARGET === "swift" ? "http://localhost:8081" : "http://localhost:9081");
const PRODUCT = __ENV.PRODUCT_URL || (TARGET === "swift" ? "http://localhost:8082" : "http://localhost:9082");
const ORDER   = __ENV.ORDER_URL   || (TARGET === "swift" ? "http://localhost:8083" : "http://localhost:9083");

// Endpoint-level latency, so per-endpoint breakdowns can be published in the
// repository without re-running anything.
const dGetUsers    = new Trend("ep_get_users", true);
const dGetProducts = new Trend("ep_get_products", true);
const dPostUsers   = new Trend("ep_post_users", true);
const dPostOrders  = new Trend("ep_post_orders", true);
const errAll       = new Rate("sut_error_rate");
const reqAll       = new Counter("sut_requests_total");
const dAll         = new Trend("sut_request_duration", true);

const STAGES = {
  // Shape preserved from the original suite, duration compressed so that five
  // independent repetitions of every scenario fit the measurement budget.
  load:   [ { duration: "30s", target: 10 },
            { duration: "60s", target: 50 },
            { duration: "90s", target: 100 },
            { duration: "30s", target: 0 } ],

  stress: [ { duration: "30s", target: 50 },
            { duration: "45s", target: 200 },
            { duration: "45s", target: 500 },
            { duration: "45s", target: 800 },
            { duration: "15s", target: 0 } ],

  spike:  [ { duration: "30s", target: 20 },
            { duration: "15s", target: 200 },
            { duration: "45s", target: 200 },
            { duration: "15s", target: 20 },
            { duration: "30s", target: 20 },
            { duration: "15s", target: 0 } ],

  soak:   [ { duration: "30s",  target: 30 },
            { duration: "180s", target: 30 },
            { duration: "30s",  target: 0 } ],
};

export const options = {
  stages: STAGES[SCENARIO],
  // No thresholds. A failed threshold aborts the run and this suite must
  // produce a complete record of what happened, including saturation.
  thresholds: {},
  discardResponseBodies: false,
  summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max", "count"],
  noConnectionReuse: false,
};

function jsonHeaders() {
  return { "Content-Type": "application/json", "Accept": "application/json" };
}

function randomInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function uniqueEmail() {
  const vu = typeof __VU   !== "undefined" ? __VU   : "s";
  const it = typeof __ITER !== "undefined" ? __ITER : 0;
  return `u_vu${vu}_it${it}_${Date.now()}_${randomInt(100000, 999999)}@test.com`;
}

function track(res, trend) {
  const ms = res.timings.duration;
  trend.add(ms);
  dAll.add(ms);
  errAll.add(res.status >= 400 || res.status === 0);
  reqAll.add(1);
  return res;
}

export function setup() {
  // Seed a small fixed catalogue.
  const userIds = [];
  const productIds = [];
  for (let i = 0; i < 5; i++) {
    const u = http.post(`${USER}/users`,
      JSON.stringify({ name: `SeedUser${i}`, email: uniqueEmail(), password: "Seed1234!" }),
      { headers: jsonHeaders() });
    if (u.status === 201 || u.status === 200) {
      try { const d = JSON.parse(u.body); if (d.id) userIds.push(d.id); } catch (e) { /* ignore */ }
    }
    const p = http.post(`${PRODUCT}/products`,
      JSON.stringify({ name: `SeedProduct${i}`, price: randomInt(10, 500), stock: 100000 }),
      { headers: jsonHeaders() });
    if (p.status === 201 || p.status === 200) {
      try { const d = JSON.parse(p.body); if (d.id) productIds.push(d.id); } catch (e) { /* ignore */ }
    }
  }

  // Warm-up happens in a separate process before the sampler starts, see
  // scenarios/warmup.js. Anything issued from here would be invisible to the
  // client-side metrics yet still counted in the server's own histogram, which
  // is exactly the mismatch that made the two measurement points incomparable.

  console.log(`setup done target=${TARGET} scenario=${SCENARIO} users=${userIds.length} products=${productIds.length}`);
  return { userIds, productIds, startedAt: Date.now() };
}

export default function (data) {
  const { userIds, productIds } = data;

  if (SCENARIO === "stress") {
    group("GET /users", () => track(http.get(`${USER}/users`), dGetUsers));
    sleep(0.1);
    group("POST /users", () => track(http.post(`${USER}/users`,
      JSON.stringify({ name: "StressUser", email: uniqueEmail(), password: "Stress123!" }),
      { headers: jsonHeaders() }), dPostUsers));
    sleep(0.1);
    return;
  }

  if (SCENARIO === "spike") {
    group("GET /products", () => track(http.get(`${PRODUCT}/products`), dGetProducts));
    sleep(0.2);
    group("GET /users", () => track(http.get(`${USER}/users`), dGetUsers));
    sleep(0.2);
    return;
  }

  if (SCENARIO === "soak") {
    // 80 / 20 read-write mix, the same ratio the original soak test used.
    const it = typeof __ITER !== "undefined" ? __ITER : 0;
    if (it % 5 === 0) {
      group("POST /users", () => track(http.post(`${USER}/users`,
        JSON.stringify({ name: "SoakUser", email: uniqueEmail(), password: "Soak123!" }),
        { headers: jsonHeaders() }), dPostUsers));
    } else {
      group("GET /products", () => track(http.get(`${PRODUCT}/products`), dGetProducts));
    }
    sleep(1);
    return;
  }

  // load
  group("GET /users", () => track(http.get(`${USER}/users`), dGetUsers));
  sleep(0.5);
  group("GET /products", () => track(http.get(`${PRODUCT}/products`), dGetProducts));
  sleep(0.5);
  group("POST /users", () => track(http.post(`${USER}/users`,
    JSON.stringify({ name: "LoadUser", email: uniqueEmail(), password: "Test1234!" }),
    { headers: jsonHeaders() }), dPostUsers));
  sleep(0.5);
  group("POST /orders", () => {
    if (userIds.length === 0 || productIds.length === 0) return;
    const uid = userIds[randomInt(0, userIds.length - 1)];
    const pid = productIds[randomInt(0, productIds.length - 1)];
    track(http.post(`${ORDER}/orders`,
      JSON.stringify({ userId: uid, items: [{ productId: pid, quantity: 1 }] }),
      { headers: jsonHeaders() }), dPostOrders);
  });
  sleep(randomInt(1, 3));
}

export function handleSummary(data) {
  // --summary-export is deprecated in k6 v1.x, so the run summary is written
  // from the script itself to a path the driver controls.
  const out = {};
  out[__ENV.SUMMARY_PATH || "summary.json"] = JSON.stringify(data, null, 2);
  return out;
}
