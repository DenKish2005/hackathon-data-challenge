// Browser/API contract test. Model output is explicitly mocked, not an accuracy measurement.
import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
import { conversations } from "../src/data.js";
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
    route.fulfill({
      json: {
        status: "configured",
        provider: "openai_compatible",
        model: "test-contract",
        is_mock: false,
      },
    }),
  );
  await page.route("**/api/evaluate*", (route) =>
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
  // Keep an appeal tied to the fixture's original evaluation before replacing it.
  await page
    .getByRole("button", { name: "Оспорить оценку", exact: true })
    .click();
  await page
    .getByLabel("Причина апелляции")
    .fill("Проверить исходный результат до нового запуска модели.");
  await page
    .getByRole("button", { name: "Отправить на пересмотр", exact: true })
    .click();
  await page
    .getByText("Оценивание и история запусков", { exact: true })
    .click();
  await page.getByText(/Провайдер openai_compatible/).waitFor();
  await page
    .getByRole("button", { name: "Оценить диалог", exact: true })
    .click();
  await page
    .getByRole("alert")
    .filter({ hasText: "Модель недоступна" })
    .waitFor();
  await page.unroute("**/api/evaluate*");
  let payload;
  let successfulResponse;
  let polls = 0;
  await page.route("**/api/workspace-evaluations/test-job", (route) => {
    polls++;
    return route.fulfill({
      json:
        polls === 1
          ? { jobId: "test-job", status: "running" }
          : {
              jobId: "test-job",
              status: "completed",
              result: successfulResponse,
            },
    });
  });
  await page.route("**/api/evaluate*", async (route) => {
    assert.equal(
      new URL(route.request().url()).searchParams.get("async_job"),
      "true",
    );
    payload = route.request().postDataJSON();
    const m = payload.messages[0];
    successfulResponse = {
      evaluationId: "test-1",
      model: "test-contract",
      is_mock: false,
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
    };
    await route.fulfill({
      status: 202,
      json: { jobId: "test-job", status: "queued", cached: false },
    });
  });
  await page
    .getByRole("button", { name: "Оценить диалог", exact: true })
    .click();
  await page.getByText(/AI: test-contract/).waitFor();
  assert.equal(payload.criteria.length, 8);
  assert.ok(payload.messages.some((m) => m.role === "operator"));
  assert.equal(payload.force, false);
  assert.equal(
    polls,
    2,
    "Async jobs must be polled through running to completion",
  );
  assert.equal(await page.getByRole("alert").count(), 0);
  // An appeal from an earlier run must never overwrite the newly returned result.
  const firstId = payload.conversation_id;
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Апелляции" })
    .click();
  await page.getByRole("button", { name: "Рассмотреть", exact: true }).click();
  await page
    .getByRole("alert")
    .filter({ hasText: "Диалог переоценён после этой апелляции" })
    .waitFor();
  assert.equal(
    await page
      .getByRole("button", { name: "Сохранить и пересчитать", exact: true })
      .isDisabled(),
    true,
  );
  await page.keyboard.press("Escape");
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Диалоги" })
    .click();
  await page
    .getByRole("button", { name: `Выбрать диалог ${firstId}`, exact: true })
    .click();
  await page
    .getByRole("button", { name: "Открыть аналитику", exact: true })
    .click();
  await page
    .getByText("Оценивание и история запусков", { exact: true })
    .click();
  await page.getByText(/AI: test-contract/).waitFor();
  assert.equal(await page.getByRole("alert").count(), 0);

  // Switching the selected dialogue must not attach an in-flight result to it.
  const otherId = await page
    .getByLabel("Выбрать другой диалог")
    .locator("option")
    .evaluateAll((options) => options.map((o) => o.value));
  const secondId = otherId.find((id) => id !== firstId);
  await page.unroute("**/api/evaluate*");
  let releaseEvaluation;
  const evaluationStarted = new Promise((resolve) => {
    page.route("**/api/evaluate*", (route) => {
      releaseEvaluation = route;
      resolve();
    });
  });
  await page
    .getByRole("button", { name: "Оценить диалог", exact: true })
    .click();
  await evaluationStarted;
  assert.equal(
    await page
      .getByRole("button", { name: "Анализируется…", exact: true })
      .isDisabled(),
    true,
  );
  await page.getByLabel("Выбрать другой диалог").selectOption(secondId);
  await releaseEvaluation.fulfill({
    json: {
      evaluationId: "test-delayed",
      model: "delayed-model",
      passes: 2,
      tokens: 1,
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
        reason: "Проверяется исходный выбранный диалог",
        evidenceId: payload.messages[0].id,
        quote: payload.messages[0].text,
        checkedMessageIds: [payload.messages[0].id],
        confidence: 0.8,
      })),
    },
  });
  await page
    .getByText("Обработка завершена: 1/1 успешно", { exact: true })
    .waitFor();
  assert.equal(
    await page.getByLabel("Выбрать другой диалог").inputValue(),
    secondId,
  );
  assert.equal(await page.getByText(/AI: delayed-model/).count(), 0);

  // A delayed history response from the previous dialogue must not leak into the next one.
  let releaseHistory;
  const historyStarted = new Promise((resolve) => {
    page.route("**/api/history/**", (route) => {
      releaseHistory = route;
      resolve();
    });
  });
  await page.getByRole("button", { name: "История AI-оценок" }).click();
  await historyStarted;
  await page.getByLabel("Выбрать другой диалог").selectOption(firstId);
  await releaseHistory
    .fulfill({
      json: [
        {
          evaluationId: "old-history",
          model: "wrong-history",
          createdAt: "yesterday",
          checklistVersion: 1,
          score: 20,
          results: [],
          summary: "stale history",
        },
      ],
    })
    .catch(() => {});
  assert.equal(
    await page.getByText("stale history", { exact: true }).count(),
    0,
  );

  // Updating a pending dialogue in place must reveal its real criteria and explanation.
  const pendingId = conversations.find(
    (dialog) => dialog.status === "pending",
  ).id;
  await page.getByLabel("Выбрать другой диалог").selectOption(pendingId);
  assert.equal(
    await page.locator(".ca-score-ring").getAttribute("aria-label"),
    "Итоговый балл ещё не рассчитан",
  );
  await page.unroute("**/api/evaluate*");
  await page.route("**/api/evaluate*", async (route) => {
    const pendingPayload = route.request().postDataJSON();
    assert.equal(pendingPayload.conversation_id, pendingId);
    const message = pendingPayload.messages[0];
    await route.fulfill({
      json: {
        ...successfulResponse,
        is_mock: true,
        scoreProvisional: true,
        evaluationId: "test-pending-ready",
        checklistVersion: pendingPayload.version,
        criteriaSnapshot: pendingPayload.criteria,
        results: successfulResponse.results.map((result) => ({
          ...result,
          evidenceId: result.criterionId === "1" ? "" : message.id,
          quote: result.criterionId === "1" ? "" : message.text,
          evidenceBasis: result.criterionId === "1" ? "absence" : "direct",
          reviewRecommended: result.criterionId === "1",
          checkedMessageIds: [message.id],
        })),
      },
    });
  });
  await page
    .getByRole("button", { name: "Оценить диалог", exact: true })
    .click();
  await page
    .getByText("Обработка завершена: 1/1 успешно", { exact: true })
    .waitFor();
  assert.equal(
    await page.getByLabel("Выбрать другой диалог").inputValue(),
    pendingId,
  );
  assert.match(
    await page.locator(".ca-score-ring").getAttribute("aria-label"),
    /100/,
  );
  assert.equal(await page.locator(".ca-criterion-row").count(), 8);
  assert.equal(
    await page.locator('.ca-criterion-row[aria-pressed="true"]').count(),
    1,
  );
  assert.match(
    await page.locator(".ca-explanation").innerText(),
    /Контрактный тест интерфейса, не оценка модели/,
  );
  await page
    .getByRole("button", {
      name: "Критерий: Установление контакта",
      exact: true,
    })
    .click();
  await page
    .getByText(/Предварительная оценка · нужна проверка специалистом/)
    .waitFor();
  await page.getByText(/Действие не найдено в проверенном диалоге/).waitFor();
  assert.equal(
    await page
      .getByRole("button", { name: "Показать реплику", exact: true })
      .isDisabled(),
    true,
  );
  assert.match(
    await page.locator(".analysis-source").innerText(),
    /Тестовый результат/,
  );
  assert.equal(
    await page.getByText(/AI: test-contract/).count(),
    0,
    "Mock output must not claim a model analysis",
  );
  await page.unroute("**/api/evaluate*");
  await page.route("**/api/evaluate*", (route) =>
    route.fulfill({
      status: 202,
      json: { jobId: "failed-job", status: "queued" },
    }),
  );
  await page.route("**/api/workspace-evaluations/failed-job", (route) =>
    route.fulfill({
      json: {
        jobId: "failed-job",
        status: "failed",
        error: "Проверка не выполнена — ошибка модели",
      },
    }),
  );
  await page
    .getByRole("button", { name: "Оценить диалог", exact: true })
    .click();
  await page.getByRole("alert").filter({ hasText: "ошибка модели" }).waitFor();
  assert.equal(
    await page
      .getByRole("button", { name: "Оценить диалог", exact: true })
      .isEnabled(),
    true,
  );

  // A late startup GET must preserve edits made while connecting, and must not PUT them over another revision.
  const workspacePage = await browser.newPage();
  await workspacePage.route("**/api/health", (route) =>
    route.fulfill({ json: { status: "model_unavailable" } }),
  );
  let pendingWorkspace;
  let writes = 0;
  const workspaceStarted = new Promise((resolve) => {
    workspacePage.route("**/api/workspace", (route) => {
      if (route.request().method() === "GET") {
        pendingWorkspace = route;
        resolve();
      } else {
        writes++;
        route.fulfill({ json: { revision: 10 } });
      }
    });
  });
  await workspacePage.goto(process.env.BASE_URL || "http://127.0.0.1:8000");
  await workspaceStarted;
  const originalWorkspace = await workspacePage.evaluate(() => ({
    dialogs: JSON.parse(localStorage.getItem("freedom-cqa-dialogs")),
    criteria: JSON.parse(localStorage.getItem("freedom-cqa-criteria")),
    version: JSON.parse(localStorage.getItem("freedom-cqa-version")),
    appeals: JSON.parse(localStorage.getItem("freedom-cqa-appeals")),
  }));
  await workspacePage
    .getByRole("navigation")
    .getByRole("button", { name: "Критерии оценки" })
    .click();
  await workspacePage
    .getByRole("button", { name: "Настроить", exact: true })
    .first()
    .click();
  await workspacePage
    .getByLabel("Название", { exact: true })
    .fill("Локальная правка во время подключения");
  await workspacePage
    .getByRole("button", { name: "Сохранить", exact: true })
    .click();
  await pendingWorkspace.fulfill({
    json: { revision: 9, data: originalWorkspace },
  });
  await workspacePage
    .getByText(/Данные изменены во время подключения/)
    .waitFor();
  assert.equal(
    await workspacePage
      .getByRole("heading", {
        name: "Локальная правка во время подключения",
        exact: true,
      })
      .count(),
    1,
  );
  await workspacePage.waitForTimeout(1700);
  assert.equal(writes, 0);
  await workspacePage.close();
  // Restoration must finish even if the server serializes object keys in a different order.
  const restorePage = await browser.newPage();
  const restoredWorkspace = {
    version: originalWorkspace.version,
    appeals: originalWorkspace.appeals,
    criteria: structuredClone(originalWorkspace.criteria),
    dialogs: originalWorkspace.dialogs,
  };
  restoredWorkspace.criteria[0].title = "Критерий с сервера";
  let restoredWrites = [];
  await restorePage.route("**/api/workspace", (route) => {
    if (route.request().method() === "GET")
      route.fulfill({ json: { revision: 12, data: restoredWorkspace } });
    else {
      restoredWrites.push(route.request().postDataJSON());
      route.fulfill({ json: { revision: 13 } });
    }
  });
  await restorePage.route("**/api/health", (route) =>
    route.fulfill({ json: { status: "model_unavailable" } }),
  );
  await restorePage.goto(process.env.BASE_URL || "http://127.0.0.1:8000");
  await restorePage
    .getByText("Рабочее пространство восстановлено с сервера", { exact: true })
    .waitFor();
  await restorePage
    .getByRole("navigation")
    .getByRole("button", { name: "Критерии оценки" })
    .click();
  await restorePage
    .getByRole("heading", { name: "Критерий с сервера", exact: true })
    .waitFor();
  await restorePage.waitForTimeout(1700);
  assert.equal(restoredWrites.length, 0);
  await restorePage
    .getByRole("button", { name: "Настроить", exact: true })
    .first()
    .click();
  await restorePage
    .getByLabel("Название", { exact: true })
    .fill("Правка после восстановления");
  await restorePage
    .getByRole("button", { name: "Сохранить", exact: true })
    .click();
  await restorePage
    .getByText("Изменения сохранены на сервере", { exact: true })
    .waitFor();
  assert.equal(restoredWrites.length, 1);
  assert.equal(restoredWrites[0].revision, 12);
  assert.equal(
    restoredWrites[0].data.criteria[0].title,
    "Правка после восстановления",
  );
  await restorePage.close();
  console.log(
    "PASS: transcript/checklist request, visible model failure, stale appeal protection, selected-dialogue race, stale history, pending-to-ready update and workspace hydration protection. LLM output mocked.",
  );
} finally {
  await browser.close();
}
