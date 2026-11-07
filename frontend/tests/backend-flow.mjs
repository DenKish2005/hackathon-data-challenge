// Real HTTP/browser integration with an isolated SQLite database and explicit mock provider.
// No route interception, organizer data or semantic-accuracy claims.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium, expect } from "@playwright/test";

const root = fileURLToPath(new URL("../../", import.meta.url));
const temporary = await mkdtemp(path.join(tmpdir(), "cqa-browser-"));
const port = Number(process.env.CQA_TEST_PORT || 8016);
const base = `http://127.0.0.1:${port}`;
const python =
  process.env.CQA_TEST_PYTHON ||
  path.join(
    root,
    ".venv",
    process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
  );
const backend = spawn(
  python,
  [
    "-m",
    "uvicorn",
    "cqa.api:app",
    "--host",
    "127.0.0.1",
    "--port",
    String(port),
  ],
  {
    cwd: root,
    env: {
      ...process.env,
      LLM_PROVIDER: "mock",
      CQA_STRATEGY: "two_pass",
      DATABASE_URL: `sqlite:///${path.join(temporary, "workspace.db")}`,
      CQA_FRONTEND_DIR: path.join(root, "frontend/dist"),
    },
    stdio: ["ignore", "pipe", "pipe"],
  },
);
let log = "";
for (const stream of [backend.stdout, backend.stderr])
  stream.on("data", (chunk) => {
    log = (log + chunk).slice(-5000);
  });
let browser;
async function serverJson(route) {
  const response = await fetch(base + route);
  assert.equal(response.ok, true, `GET ${route}: ${response.status}`);
  return response.json();
}
async function waitForValue(read, check, message) {
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    const result = await read();
    if (check(result)) return result;
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw Error(message);
}
const fixture = {
  records: [
    {
      conversation_id: "browser-e2e-chat",
      language: "RU",
      channel: "agent chat",
      topic: "Синтетический тест интеграции",
      transcript: [
        {
          speaker: "client",
          timestamp: "00:00",
          text: "Здравствуйте. Как изменить контактный телефон?",
        },
        {
          speaker: "operator",
          timestamp: "00:10",
          text: "Здравствуйте! Откройте профиль и выберите раздел контактных данных.",
        },
        { speaker: "client", timestamp: "00:20", text: "Спасибо, получилось." },
        {
          speaker: "operator",
          timestamp: "00:30",
          text: "Спасибо за обращение. Хорошего дня!",
        },
      ],
    },
  ],
};
try {
  await waitForValue(
    async () => {
      if (backend.exitCode !== null) throw Error(`Backend exited: ${log}`);
      return fetch(`${base}/api/ready`)
        .then((r) => r.ok)
        .catch(() => false);
    },
    Boolean,
    "Backend did not become ready",
  );
  assert.equal((await serverJson("/api/health")).is_mock, true);
  browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || "/usr/bin/chromium",
    args: ["--no-sandbox"],
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.goto(base);
  await expect(page.locator(".sync-status")).toContainText(
    /подключено|восстановлено/,
  );
  await page
    .getByRole("button", { name: "Загрузить диалоги", exact: true })
    .click();
  await page
    .getByLabel("Ответ API", { exact: true })
    .fill(JSON.stringify(fixture));
  await page
    .getByRole("button", { name: "Импортировать", exact: true })
    .click();
  await waitForValue(
    () => serverJson("/api/workspace"),
    (w) => w.data?.dialogs.some((d) => d.id === "browser-e2e-chat"),
    "Imported conversation was not persisted",
  );
  assert.equal(
    (await serverJson("/api/conversations/browser-e2e-chat")).conversation_id,
    "browser-e2e-chat",
  );
  await page
    .getByRole("button", {
      name: "Выбрать диалог browser-e2e-chat",
      exact: true,
    })
    .click();
  await page
    .getByRole("button", { name: "Открыть аналитику", exact: true })
    .click();
  await page
    .getByText("Оценивание и история запусков", { exact: true })
    .click();
  const jobStarted = page.waitForResponse((r) =>
    r.url().includes("/api/evaluate?async_job=true"),
  );
  await page
    .getByRole("button", { name: "Оценить диалог", exact: true })
    .click();
  const startResponse = await jobStarted;
  const started = await startResponse.json();
  assert.equal(startResponse.status(), 202, JSON.stringify(started));
  assert.ok(started.jobId);
  await expect(
    page.getByRole("button", { name: "Оценить диалог", exact: true }),
  ).toBeEnabled({ timeout: 15000 });
  await expect(
    page
      .getByRole("group", { name: "Результаты критериев" })
      .getByRole("button"),
  ).toHaveCount(8);
  await expect(
    page.getByText("Тестовый результат · без AI", { exact: true }),
  ).toBeVisible();
  const assessed = await waitForValue(
    () => serverJson("/api/workspace"),
    (w) =>
      w.data?.dialogs.find((d) => d.id === "browser-e2e-chat")?.results
        ?.length === 8,
    "Assessment was not persisted",
  );
  const dialog = assessed.data.dialogs.find((d) => d.id === "browser-e2e-chat");
  assert.equal(dialog.is_mock, true);
  assert.equal(dialog.criteriaSnapshot.length, 8);
  assert.equal(dialog.checklistVersion, assessed.data.version);
  assert.ok(
    dialog.results.every(
      (r) => r.reason && (r.evidenceId || r.checkedMessageIds.length),
    ),
  );
  await page
    .getByRole("button", { name: "Оспорить оценку", exact: true })
    .click();
  const appealComment =
    "Проверить исходную реплику оператора: синтетическая апелляция.";
  await page.getByLabel("Причина апелляции").fill(appealComment);
  await page
    .getByRole("button", { name: "Отправить на пересмотр", exact: true })
    .click();
  await waitForValue(
    () => serverJson("/api/workspace"),
    (w) => w.data?.appeals.some((a) => a.comment === appealComment),
    "Appeal was not persisted",
  );
  // Exercise navigation after submission: this was the user's reported freezing path.
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Апелляции" })
    .click();
  await expect(page.getByText(appealComment, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Рассмотреть", exact: true }).click();
  await page.getByLabel(/^Ответ после проверки/).selectOption("Да");
  await page
    .getByLabel(/^Обоснование решения/)
    .fill("Проверяющий подтвердил приветствие по исходной реплике оператора.");
  await page
    .getByRole("button", { name: "Сохранить и пересчитать", exact: true })
    .click();
  const reviewed = await waitForValue(
    () => serverJson("/api/workspace"),
    (w) =>
      w.data?.appeals.some(
        (a) => a.comment === appealComment && a.status === "resolved",
      ),
    "Human review was not persisted",
  );
  const reviewedDialog = reviewed.data.dialogs.find(
    (d) => d.id === "browser-e2e-chat",
  );
  assert.equal(reviewedDialog.results[0].answer, "Да");
  assert.ok(reviewedDialog.score > dialog.score);
  assert.equal(reviewedDialog.originalScore, dialog.score);
  await page.reload();
  await expect(page.locator(".sync-status")).toContainText("восстановлено");
  await expect(page.getByText(appealComment, { exact: true })).toBeVisible();
  // A fresh browser must recover the result and appeal from SQLite, not localStorage.
  const fresh = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  fresh.on("pageerror", (error) => pageErrors.push(error.message));
  await fresh.goto(`${base}/#dialog/browser-e2e-chat`);
  await expect(fresh.locator(".sync-status")).toContainText("восстановлено");
  await expect(
    fresh.getByRole("heading", { name: "Анализ разговора", exact: true }),
  ).toBeVisible();
  await expect(
    fresh
      .getByRole("group", { name: "Результаты критериев" })
      .getByRole("button"),
  ).toHaveCount(8);
  assert.equal((await serverJson("/api/history/browser-e2e-chat")).length, 1);
  assert.deepEqual(pageErrors, []);
  await page.close();
  // Editing a rule creates an immutable version; the next run must use it.
  await fresh
    .getByRole("navigation")
    .getByRole("button", { name: /^Диалоги/ })
    .click();
  await fresh
    .getByRole("button", {
      name: "Настроить критерий: Установление контакта",
      exact: true,
    })
    .click();
  await fresh
    .getByLabel(/^Правило оценки/)
    .fill(
      "Оператор поздоровался и представился. Изменённое правило интеграционного теста.",
    );
  await fresh.getByRole("button", { name: "Сохранить", exact: true }).click();
  await waitForValue(
    () => serverJson("/api/workspace"),
    (w) => w.data?.version > dialog.checklistVersion,
    "Updated checklist was not persisted",
  );
  await fresh
    .getByRole("button", {
      name: "Выбрать диалог browser-e2e-chat",
      exact: true,
    })
    .click();
  await fresh
    .getByRole("button", { name: "Открыть аналитику", exact: true })
    .click();
  await fresh
    .getByText("Оценивание и история запусков", { exact: true })
    .click();
  await fresh
    .getByRole("button", { name: "Оценить диалог", exact: true })
    .click();
  await expect(
    fresh.getByRole("button", { name: "Оценить диалог", exact: true }),
  ).toBeEnabled({ timeout: 15000 });
  const history = await waitForValue(
    () => serverJson("/api/history/browser-e2e-chat"),
    (h) => h.length === 2,
    "Changed checklist did not produce a new evaluation",
  );
  assert.notEqual(history[0].evaluationId, history[1].evaluationId);
  assert.ok(history[0].checklistVersion > history[1].checklistVersion);
  assert.notEqual(
    history[0].criteriaSnapshot[0].description,
    history[1].criteriaSnapshot[0].description,
  );
  assert.equal(
    history[1].criteriaSnapshot[0].description,
    dialog.criteriaSnapshot[0].description,
  );
  assert.deepEqual(pageErrors, []);
  console.log(
    "PASS: real backend import → async mock evaluation → eight criteria → appeal → navigation → SQLite restore in a fresh browser → changed checklist/new run with immutable history; no JavaScript errors.",
  );
} catch (error) {
  console.error(log);
  throw error;
} finally {
  await browser?.close();
  if (backend.exitCode === null) {
    const ended = once(backend, "exit");
    backend.kill("SIGTERM");
    const timer = setTimeout(() => backend.kill("SIGKILL"), 3000);
    await ended;
    clearTimeout(timer);
  }
  await rm(temporary, { recursive: true, force: true });
}
