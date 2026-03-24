import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  stages: [
    { duration: "1m", target: 20 },
    { duration: "3m", target: 50 },
    { duration: "1m", target: 0 },
  ],
  thresholds: {
    http_req_duration: ["p(95)<1000"],
    http_req_failed: ["rate<0.05"],
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
  // Mix of read operations
  const endpoints = [
    "/health",
    "/api/v1/tasks",
    "/api/v1/state",
    "/api/v1/proposals",
  ];

  const endpoint = endpoints[Math.floor(Math.random() * endpoints.length)];
  const needsAuth = endpoint !== "/health";

  const res = http.get(`${BASE_URL}${endpoint}`, {
    headers: needsAuth ? headers() : { "Content-Type": "application/json" },
  });

  check(res, {
    "status is 2xx": (r) => r.status >= 200 && r.status < 300,
  });

  sleep(0.5 + Math.random());
}
