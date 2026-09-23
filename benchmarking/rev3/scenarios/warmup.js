/**
 * Warm-up pass, run as its own k6 process before measurement begins.
 *
 * Keeping the warm-up in a separate process is what makes the server-side
 * aggregation window mean what it says. When the warm-up ran inside the
 * measured script's setup(), its requests were invisible to the client-side
 * metrics but still landed in the service's own histogram, so the server
 * percentile was computed over a population the client percentile did not
 * contain. The sampler is started only after this process exits.
 *
 * It also seeds the catalogue, so the measured run starts from a populated
 * table on both stacks.
 */
import http from "k6/http";

const TARGET  = __ENV.TARGET || "swift";
const USER    = __ENV.USER_URL    || (TARGET === "swift" ? "http://localhost:8081" : "http://localhost:9081");
const PRODUCT = __ENV.PRODUCT_URL || (TARGET === "swift" ? "http://localhost:8082" : "http://localhost:9082");

const ITERATIONS = parseInt(__ENV.WARMUP_REQUESTS || "1000");

export const options = {
  vus: 4,
  iterations: ITERATIONS,
  thresholds: {},
  discardResponseBodies: true,
};

function jsonHeaders() {
  return { "Content-Type": "application/json", "Accept": "application/json" };
}

function randomInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

export function setup() {
  for (let i = 0; i < 5; i++) {
    http.post(`${USER}/users`,
      JSON.stringify({ name: `SeedUser${i}`, email: `seed_${i}_${Date.now()}_${randomInt(1e5, 1e6)}@test.com`,
                       password: "Seed1234!" }), { headers: jsonHeaders() });
    http.post(`${PRODUCT}/products`,
      JSON.stringify({ name: `SeedProduct${i}`, price: randomInt(10, 500), stock: 100000 }),
      { headers: jsonHeaders() });
  }
}

export default function () {
  http.get(`${USER}/users`);
  http.get(`${PRODUCT}/products`);
  // Exercise the hashing path too, so just in time compilation covers the
  // processor bound route and not only the read routes.
  if ((typeof __ITER !== "undefined" ? __ITER : 0) % 10 === 0) {
    http.post(`${USER}/users`,
      JSON.stringify({ name: "WarmUser",
                       email: `warm_${__VU}_${__ITER}_${Date.now()}_${randomInt(1e5, 1e6)}@test.com`,
                       password: "Warm1234!" }), { headers: jsonHeaders() });
  }
}

export function handleSummary() {
  return {};
}
