// Browser regressions with synthetic fixtures. No external requests or model calls.
import assert from "node:assert/strict";
import { chromium, expect } from "@playwright/test";
import { conversations } from "../src/data.js";

const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || "/usr/bin/chromium",
  args: ["--no-sandbox"],
});
const base = process.env.BASE_URL || "http://127.0.0.1:4173";
const rule = {
  id: "custom",
  title: "Динамический критерий",
  description: "Синтетическое правило",
  type: "scale",
  weight: 1,
  scale: [0, 1.005, 100],
  naAllowed: true,
  naCondition: "Нет события",
};
const fixture = {
  ...structuredClone(conversations[0]),
  id: "hardening-synthetic",
  status: "done",
  criteriaSnapshot: [rule],
  results: [
    {
      criterionId: rule.id,
      answer: 1.005,
      reason: "Требует проверки",
      evidenceId: "m2",
      reviewRecommended: true,
    },
  ],
  score: 1.01,
  scoreProvisional: true,
  originalScore: 1.01,
  reviewRevision: 0,
};
async function open(dialog, criteria = [rule]) {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/api/**", (route) =>
    route.fulfill({
      json: route.request().url().endsWith("/workspace")
        ? route.request().method() === "GET"
          ? {
              revision: 1,
              data: { dialogs: [dialog], criteria, version: 1, appeals: [] },
            }
          : { revision: 2 }
        : { status: "model_unavailable" },
    }),
  );
  await page.goto(base);
  await expect(page.locator(".sync-status")).toContainText("восстановлено");
  return { page, errors };
}
try {
  const { page, errors } = await open(fixture);
  await expect(page.locator(".desk-chat-row")).toContainText("1,01");
  await expect(page.locator(".desk-chat-row")).toContainText("На проверке");
  await page
    .getByRole("group", { name: "Статус диалога" })
    .getByRole("button", { name: /^На проверке/ })
    .click();
  await expect(page.locator(".desk-chat-row")).toHaveCount(1);
  await page
    .getByRole("button", { name: `Выбрать диалог ${fixture.id}`, exact: true })
    .click();
  await expect(page.locator(".desk-selected-score")).toContainText(
    "Предварительная оценка",
  );
  await page
    .getByRole("button", { name: "Открыть аналитику", exact: true })
    .click();
  await expect(page.locator(".ca-score-ring strong")).toHaveText("1,01");
  await expect(page.getByText(/До пересмотра:/)).toHaveCount(0);
  await expect(
    page.getByText("Предварительная оценка диалога", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(/Предварительная оценка · нужна проверка/),
  ).toBeVisible();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Общая статистика", exact: true })
    .click();
  await expect(page.locator(".criteria-summary .progress-item")).toHaveCount(1);
  await expect(page.locator(".criteria-summary")).toContainText(rule.title);
  await expect(
    page
      .locator(".stat")
      .filter({ hasText: "Требуют внимания" })
      .locator(".stat-value"),
  ).toContainText("01");
  assert.deepEqual(errors, []);
  await page.close();

  const allNA = {
    ...fixture,
    score: null,
    scoreProvisional: false,
    results: [
      {
        criterionId: rule.id,
        answer: "N/A",
        reason: "Событие отсутствует",
        evidenceId: "m1",
      },
    ],
  };
  const optional = await open(allNA);
  await optional.page
    .getByRole("button", { name: `Выбрать диалог ${fixture.id}`, exact: true })
    .click();
  await expect(optional.page.locator(".desk-selected-score")).toContainText(
    "0 применимых критериев · 1 N/A",
  );
  await expect(optional.page.locator(".desk-average strong")).toContainText(
    "—",
  );
  await expect(
    optional.page.getByText("Диалог ожидает оценки", { exact: true }),
  ).toHaveCount(0);
  await optional.page
    .getByRole("button", { name: "Открыть аналитику", exact: true })
    .click();
  await expect(optional.page.locator(".ca-score-ring strong")).toHaveText("—");
  await expect(
    optional.page.getByText("Нет применимых критериев с баллом", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    optional.page.getByRole("button", {
      name: `Критерий: ${rule.title}`,
      exact: true,
    }),
  ).toContainText("N/A");
  await optional.page
    .getByRole("navigation")
    .getByRole("button", { name: "Общая статистика", exact: true })
    .click();
  await expect(optional.page.locator(".criteria-summary")).toContainText(
    "Нет данных",
  );
  await expect(
    optional.page
      .locator(".stat")
      .filter({ hasText: "Средняя оценка качества" })
      .locator(".stat-value"),
  ).toContainText("—");
  await expect(
    optional.page
      .locator(".stat")
      .filter({ hasText: "Проанализировано диалогов" })
      .locator(".stat-value"),
  ).toContainText("01");
  assert.deepEqual(optional.errors, []);
  console.log(
    "PASS: decimal display, provisional review queue/filter/analysis, dynamic dashboard and all-N/A results without false zero/pending states. API mocked.",
  );
} finally {
  await browser.close();
}
