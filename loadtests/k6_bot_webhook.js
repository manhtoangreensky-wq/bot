import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

export const errorRate = new Rate("errors");

const BASE_URL = (__ENV.BASE_URL || "http://localhost:8000").replace(/\/+$/, "");
const WEBHOOK_PATH = __ENV.TELEGRAM_WEBHOOK_PATH || "/webhook/telegram/load-test-secret";
const TG_SECRET = __ENV.TELEGRAM_WEBHOOK_SECRET || "";

export const options = {
  scenarios: {
    bot_updates: {
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
    http_req_duration: ["p(50)<300", "p(95)<1200", "p(99)<3000"],
    errors: ["rate<0.01"]
  }
};

function headers() {
  const h = {
    "Content-Type": "application/json",
    "X-Load-Test-Mode": "true",
    "X-Dry-Run": "true"
  };
  if (TG_SECRET) h["X-Telegram-Bot-Api-Secret-Token"] = TG_SECRET;
  return h;
}

function telegramUpdate(text, updateId) {
  const userId = 900000000 + (__VU * 100000) + (__ITER % 100000);
  return {
    update_id: updateId,
    message: {
      message_id: updateId,
      date: Math.floor(Date.now() / 1000),
      chat: { id: userId, type: "private", first_name: "Load", username: `loadtest_${userId}` },
      from: { id: userId, is_bot: false, first_name: "Load", username: `loadtest_${userId}`, language_code: "vi" },
      text: text
    }
  };
}

function callbackUpdate(data, updateId) {
  const userId = 910000000 + (__VU * 100000) + (__ITER % 100000);
  return {
    update_id: updateId,
    callback_query: {
      id: `loadtest_cb_${updateId}`,
      from: { id: userId, is_bot: false, first_name: "Load", username: `loadtest_${userId}`, language_code: "vi" },
      message: {
        message_id: updateId,
        date: Math.floor(Date.now() / 1000),
        chat: { id: userId, type: "private", first_name: "Load" },
        text: "load test callback"
      },
      data: data
    }
  };
}

function makeUpdate() {
  const updateId = 700000000 + (__VU * 100000) + __ITER;
  const choices = [
    () => telegramUpdate("/start", updateId),
    () => telegramUpdate("tôi muốn tạo video bán hàng nước hoa", updateId),
    () => callbackUpdate("menu|video", updateId),
    () => callbackUpdate("menu|image", updateId),
    () => callbackUpdate("menu|main", updateId)
  ];
  return choices[Math.floor(Math.random() * choices.length)]();
}

export default function () {
  const res = http.post(`${BASE_URL}${WEBHOOK_PATH}`, JSON.stringify(makeUpdate()), { headers: headers(), timeout: "10s" });
  const ok = check(res, {
    "webhook: status < 500": (r) => r.status < 500,
    "webhook: responded": (r) => r.status > 0
  });
  errorRate.add(!ok);
  sleep(Math.random() * 0.2);
}
