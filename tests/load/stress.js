import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  stages: [
    { duration: "2m", target: 50 },
    { duration: "5m", target: 100 },
    { duration: "2m", target: 150 },
    { duration: "1m", target: 0 },
  ],
  thresholds: {
    http_req_duration: ["p(95)<2000"],
    http_req_failed: ["rate<0.10"],
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
  // Heavier mix including writes
  const r = Math.random();

  if (r < 0.6) {
    // 60% reads
    http.get(`${BASE_URL}/api/v1/tasks`, { headers: headers() });
  } else if (r < 0.85) {
    // 25% state reads
    http.get(`${BASE_URL}/api/v1/state`, { headers: headers() });
  } else {
    // 15% task submissions
    const payload = JSON.stringify({
      name: `stress-test-${Date.now()}`,
      description: "Stress test task submission",
      spec: {},
    });
    const res = http.post(`${BASE_URL}/api/v1/tasks`, payload, { headers: headers() });
    check(res, {
      "task created": (r) => r.status === 200 || r.status === 201,
    });
  }

  sleep(0.2 + Math.random() * 0.3);
}
