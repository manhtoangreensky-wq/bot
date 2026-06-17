import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

export const errorRate = new Rate("errors");

const BASE_URL = (__ENV.BASE_URL || "http://localhost:8000").replace(/\/+$/, "");
const WEBHOOK_PATH = __ENV.TELEGRAM_WEBHOOK_PATH || "/webhook/telegram/load-test-secret";
const TG_SECRET = __ENV.TELEGRAM_WEBHOOK_SECRET || "";

export const options = {
  scenarios: {
    mixed: {
      executor: "constant-arrival-rate",
      rate: Number(__ENV.RATE || 10),
      timeUnit: "1s",
      duration: __ENV.DURATION || "5m",
      preAllocatedVUs: Number(__ENV.VUS || 20),
      maxVUs: Number(__ENV.MAX_VUS || 100)
    }
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(50)<400", "p(95)<1500", "p(99)<3000"],
    errors: ["rate<0.01"]
  }
};

function baseHeaders() {
  return {
    "Content-Type": "application/json",
    "X-Load-Test-Mode": "true",
    "X-Dry-Run": "true"
  };
}

function botHeaders() {
  const h = baseHeaders();
  if (TG_SECRET) h["X-Telegram-Bot-Api-Secret-Token"] = TG_SECRET;
  return h;
}

function record(res, name) {
  const ok = check(res, {
    [`${name}: status < 500`]: (r) => r.status < 500,
    [`${name}: responded`]: (r) => r.status > 0
  });
  errorRate.add(!ok);
}

function syntheticUpdate() {
  const updateId = 800000000 + (__VU * 100000) + __ITER;
  const userId = 920000000 + (__VU * 100000) + (__ITER % 100000);
  return {
    update_id: updateId,
    message: {
      message_id: updateId,
      date: Math.floor(Date.now() / 1000),
      chat: { id: userId, type: "private", first_name: "Load" },
      from: { id: userId, is_bot: false, first_name: "Load", username: `loadtest_${userId}`, language_code: "vi" },
      text: Math.random() < 0.5 ? "/start" : "tạo video quảng cáo nước hoa"
    }
  };
}

export default function () {
  const r = Math.random();
  if (r < 0.55) {
    const paths = ["/health", "/api/v1/health", "/api/v1/metrics-lite", "/status"];
    const path = paths[Math.floor(Math.random() * paths.length)];
    record(http.get(`${BASE_URL}${path}`, { headers: baseHeaders(), timeout: "10s" }), `read_${path}`);
  } else if (r < 0.9) {
    record(http.post(`${BASE_URL}${WEBHOOK_PATH}`, JSON.stringify(syntheticUpdate()), { headers: botHeaders(), timeout: "10s" }), "bot_webhook");
  } else {
    const payload = JSON.stringify({
      user_id: `loadtest_${__VU}_${__ITER}`,
      category: "mixed_load_test",
      message: "dry-run mixed workload feedback",
      dry_run: true
    });
    record(http.post(`${BASE_URL}/api/v1/customer/feedback`, payload, { headers: baseHeaders(), timeout: "10s" }), "feedback_dry_run");
  }
  sleep(Math.random() * 0.2);
}
