import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

export const errorRate = new Rate("errors");

const BASE_URL = (__ENV.BASE_URL || "http://localhost:8000").replace(/\/+$/, "");
const READ_ONLY = String(__ENV.READ_ONLY || "false").toLowerCase() === "true";
const TOKEN = __ENV.OPERATOR_API_TOKEN || "";

export const options = {
  scenarios: {
    baseline: {
      executor: "constant-arrival-rate",
      rate: Number(__ENV.RATE || 5),
      timeUnit: "1s",
      duration: __ENV.DURATION || "2m",
      preAllocatedVUs: Number(__ENV.VUS || 10),
      maxVUs: Number(__ENV.MAX_VUS || 50)
    }
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(50)<400", "p(95)<1500", "p(99)<3000"],
    errors: ["rate<0.01"]
  }
};

function headers() {
  const h = {
    "Content-Type": "application/json",
    "X-Load-Test-Mode": "true",
    "X-Dry-Run": "true"
  };
  if (TOKEN) h["X-Operator-Token"] = TOKEN;
  return h;
}

function record(res, name) {
  const ok = check(res, {
    [`${name}: status < 500`]: (r) => r.status < 500,
    [`${name}: responded`]: (r) => r.status > 0
  });
  errorRate.add(!ok);
}

export default function () {
  const lightReads = [
    ["/health", "health"],
    ["/api/v1/health", "api_health"],
    ["/api/v1/metrics-lite", "metrics_lite"],
    ["/status", "status"],
    ["/asset_check", "asset_check"]
  ];
  const pick = lightReads[Math.floor(Math.random() * lightReads.length)];
  record(http.get(`${BASE_URL}${pick[0]}`, { headers: headers(), timeout: "10s" }), pick[1]);

  if (!READ_ONLY && Math.random() < 0.15) {
    const feedbackPayload = JSON.stringify({
      user_id: `loadtest_${__VU}_${__ITER}`,
      category: "load_test",
      message: "dry-run feedback load test",
      dry_run: true
    });
    record(http.post(`${BASE_URL}/api/v1/customer/feedback`, feedbackPayload, { headers: headers(), timeout: "10s" }), "feedback_dry_run");
  }

  if (!READ_ONLY && Math.random() < 0.05) {
    const billingPayload = JSON.stringify({
      user_id: `loadtest_${__VU}_${__ITER}`,
      amount: 10000,
      product_type: "load_test",
      dry_run: true
    });
    record(http.post(`${BASE_URL}/api/v1/billing/create-payment-link`, billingPayload, { headers: headers(), timeout: "10s" }), "billing_dry_run");
  }

  sleep(Math.random() * 0.2);
}
