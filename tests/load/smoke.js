import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  vus: 10,
  duration: "30s",
  thresholds: {
    http_req_duration: ["p(95)<500"],
    http_req_failed: ["rate<0.01"],
  },
};

const BASE_URL = __ENV.GATEWAY_URL || "http://localhost:8000";
const API_KEY = __ENV.API_KEY || "";

function headers() {
  const h = { "Content-Type": "application/json" };
  if (API_KEY) {
    h["Authorization"] = `Bearer ${API_KEY}`;
  }
  return h;
}

export default function () {
  // Health check (no auth required)
  const health = http.get(`${BASE_URL}/health`);
  check(health, {
    "health status 200": (r) => r.status === 200,
    "health is healthy": (r) => r.json().status === "healthy" || r.json().status === "degraded",
  });

  // List tasks
  const tasks = http.get(`${BASE_URL}/api/v1/tasks`, { headers: headers() });
  check(tasks, {
    "tasks status 200": (r) => r.status === 200,
  });

  // Get world state
  const state = http.get(`${BASE_URL}/api/v1/state`, { headers: headers() });
  check(state, {
    "state status 200": (r) => r.status === 200,
  });

  sleep(1);
}
