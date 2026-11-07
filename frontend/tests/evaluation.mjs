// Browser/API contract test. Model output is explicitly mocked, not an accuracy measurement.
import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || "/usr/bin/chromium",
  args: ["--no-sandbox"],
});
try {
  const page = await browser.newPage();
  await page.route("**/api/workspace", (route) =>
    route.fulfill({ json: { revision: 0, data: null } }),
  );
  await page.route("**/api/health", (route) =>
    route.fulfill({ json: { status: "ready", model: "test-contract" } }),
  );
  await page.route("**/api/evaluate", (route) =>
    route.fulfill({
      status: 503,
      json: { detail: "Модель недоступна — тест обработки ошибки" },
    }),
  );
  await page.goto(process.env.BASE_URL || "http://127.0.0.1:8000");
  await page.locator(".desk-chat-row").first().click();
  await page
    .getByRole("button", { name: "Открыть аналитику", exact: true })
    .click();
  await page
    .getByRole("heading", { name: "Анализ разговора", exact: true })
    .waitFor();
  await page
    .getByText("Оценивание и история запусков", { exact: true })
    .click();
  await page
    .getByRole("button", { name: "Оценить диалог", exact: true })
    .click();
  await page
    .getByRole("alert")
    .filter({ hasText: "Модель недоступна" })
    .waitFor();
  await page.unroute("**/api/evaluate");
  let payload;
  await page.route("**/api/evaluate", async (route) => {
    payload = route.request().postDataJSON();
    const m = payload.messages[0];
    await route.fulfill({
      json: {
        evaluationId: "test-1",
        model: "test-contract",
        passes: 2,
        tokens: 100,
        checklistVersion: payload.version,
        criteriaSnapshot: payload.criteria,
        score: 100,
        critical: false,
        results: payload.criteria.map((c) => ({
          criterionId: c.id,
          answer:
            c.type === "flag"
              ? "Нет"
              : c.naAllowed
                ? "N/A"
                : c.type === "scale"
                  ? Math.max(...c.scale)
                  : "Да",
          reason: "Контрактный тест интерфейса, не оценка модели",
          evidenceId: m.id,
          quote: m.text,
          checkedMessageIds: [m.id],
          confidence: 0.8,
        })),
      },
    });
  });
  await page
    .getByRole("button", { name: "Оценить диалог", exact: true })
    .click();
  await page.getByText(/AI: test-contract/).waitFor();
  assert.equal(payload.criteria.length, 8);
  assert.ok(payload.messages.some((m) => m.role === "operator"));
  assert.equal(payload.force, false);
  assert.equal(await page.getByRole("alert").count(), 0);
  console.log(
    "PASS: transcript/checklist request, visible model failure, applied evaluation response. LLM output mocked.",
  );
} finally {
  await browser.close();
}
