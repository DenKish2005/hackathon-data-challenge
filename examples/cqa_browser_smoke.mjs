// Real browser -> React -> Ollama -> SQLite test. Uses only an isolated synthetic DB.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { createWriteStream } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { createServer } from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(path.join(root, "frontend/package.json"));
const { chromium } = require("@playwright/test");
const directory = path.join(
  root,
  ".runtime",
  "browser-smoke",
  String(Date.now()),
);
await mkdir(directory, { recursive: true });
const socket = createServer();
socket.listen(0, "127.0.0.1");
await once(socket, "listening");
const port = socket.address().port;
await new Promise((resolve) => socket.close(resolve));
const base = `http://127.0.0.1:${port}`;
const python =
  process.env.CQA_PYTHON ||
  path.join(
    root,
    process.platform === "win32"
      ? ".venv/Scripts/python.exe"
      : ".venv/bin/python",
  );
const env = {
  ...process.env,
  DATABASE_URL: `sqlite:///${path.join(directory, "smoke.db")}`,
  LLM_PROVIDER: "ollama",
  LLM_BASE_URL: "http://127.0.0.1:11434",
  LLM_MODEL: "qwen3:4b",
  LLM_CONTEXT_SIZE: "16384",
  LLM_OUTPUT_LIMIT: "4096",
  LLM_CONCURRENCY: "1",
  LLM_TIMEOUT: "600",
  LLM_ATTEMPTS: "1",
  CQA_JOB_TIMEOUT: "650",
  CQA_WORKERS: "1",
  CQA_ENABLE_CRITIC: "false",
  PYTHONIOENCODING: "utf-8",
};
for (const key of [
  "FREEDOM_DATASET_URLS_FILE",
  "FREEDOM_DEV_API_URL",
  "FREEDOM_CONTROL_API_URL",
  "CQA_DATA_URL",
])
  delete env[key];
let server, browser;
const report = {
  provider: "ollama",
  model: "qwen3:4b",
  critic: false,
  checks: [],
};
async function api(endpoint, options) {
  const response = await fetch(base + endpoint, options);
  assert.ok(response.ok, `HTTP ${response.status}: ${endpoint}`);
  return response.json();
}
async function start() {
  const log = createWriteStream(
    path.join(directory, `server-${Date.now()}.log`),
  );
  server = spawn(python, ["-m", "cqa", "serve", "--port", String(port)], {
    cwd: root,
    env,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  server.stdout.pipe(log);
  server.stderr.pipe(log);
  for (let i = 0; i < 150; i++) {
    if (server.exitCode !== null) throw Error("Server exited before readiness");
    try {
      const health = await api("/api/health");
      assert.equal(health.status, "ready");
      assert.equal(health.is_mock, false);
      return;
    } catch {
      await new Promise((r) => setTimeout(r, 200));
    }
  }
  throw Error("Server not ready");
}
async function stop() {
  if (server?.exitCode === null) {
    const exited = once(server, "exit");
    server.kill();
    await exited;
  }
}
async function openDialog(page) {
  await page.goto(`${base}/#dialog/browser-synthetic`);
  await page
    .getByRole("heading", { name: "Транскрипт", exact: true })
    .waitFor();
  await page
    .getByRole("button", { name: "Оценить диалог", exact: true })
    .waitFor();
}
async function evaluate(page) {
  const response = page.waitForResponse(
    (r) =>
      r.url() === `${base}/api/evaluate` && r.request().method() === "POST",
    { timeout: 700000 },
  );
  const started = performance.now();
  await page
    .getByRole("button", { name: "Оценить диалог", exact: true })
    .click();
  const raw = await response;
  assert.equal(raw.status(), 200);
  const result = await raw.json();
  assert.equal(result.is_mock, false);
  assert.equal(result.results.length, 8);
  assert.equal(typeof result.score, "number");
  await page
    .getByRole("group", { name: "Фильтр критериев" })
    .getByRole("button", { name: /Все/ })
    .click();
  await page.locator(".rw-criterion").last().waitFor();
  assert.equal(await page.locator(".rw-criterion").count(), 8);
  assert.match(
    await page.locator(".rw-overall-score").getAttribute("aria-label"),
    new RegExp(String(result.score).replace(".", ",")),
  );
  const first = page.locator(".rw-criterion-toggle").first();
  if ((await first.getAttribute("aria-expanded")) !== "true")
    await first.click();
  await page
    .getByRole("button", {
      name: `Реплика #${result.results[0].evidenceId}`,
      exact: true,
    })
    .first()
    .click();
  assert.ok((await page.locator(".message.highlighted").count()) > 0);
  // Wait for a real workspace PUT to finish before restarting the server.
  await page
    .getByText("Изменения сохранены на сервере", { exact: true })
    .waitFor({ timeout: 20000 });
  await page.screenshot({
    path: path.join(directory, `result-v${result.checklistVersion}.png`),
    fullPage: true,
  });
  return { ...result, measuredSeconds: (performance.now() - started) / 1000 };
}
try {
  await start();
  await api("/api/datasets/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      payload: {
        isSuccess: true,
        data: {
          dataset_group_id: "SYNTHETIC-BROWSER",
          total_records: 1,
          records: [
            {
              conversation_id: "browser-synthetic",
              language: "RU",
              channel: "agent chat",
              transcript: [
                {
                  speaker: "operator",
                  timestamp: "00:01",
                  text: "Здравствуйте! Меня зовут Анна, компания Freedom Broker. Чем могу помочь?",
                },
                {
                  speaker: "client",
                  timestamp: "00:02",
                  text: "Спасибо, вопрос решён.",
                },
                {
                  speaker: "operator",
                  timestamp: "00:03",
                  text: "Спасибо за обращение. До свидания!",
                },
              ],
            },
          ],
        },
      },
    }),
  });
  browser = await chromium.launch(
    process.env.CHROMIUM_PATH
      ? { executablePath: process.env.CHROMIUM_PATH }
      : process.platform === "win32"
        ? { channel: "chrome" }
        : {},
  );
  let context = await browser.newContext({
    viewport: { width: 1440, height: 1050 },
  });
  let page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await openDialog(page);
  const first = await evaluate(page);
  report.checks.push(
    "button -> live LLM -> eight criteria -> score -> evidence -> SQLite",
  );
  report.first = {
    evaluationId: first.evaluationId,
    score: first.score,
    seconds: first.measuredSeconds,
  };
  const original = await api(`/api/evaluations/${first.evaluationId}`);
  await context.close();
  await stop();
  await start();
  context = await browser.newContext();
  page = await context.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  await openDialog(page);
  await page.locator(".rw-criterion").first().waitFor();
  assert.match(
    await page.locator(".rw-overall-score").getAttribute("aria-label"),
    new RegExp(String(first.score).replace(".", ",")),
  );
  assert.equal(
    (await api(`/api/evaluations/${first.evaluationId}`)).evaluation_id,
    first.evaluationId,
  );
  report.checks.push(
    "process restart + fresh browser context restore saved result",
  );
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Критерии оценки", exact: true })
    .click();
  await page.getByRole("button", { name: "Настроить" }).first().click();
  const title = page.getByLabel("Название", { exact: true });
  await title.fill((await title.inputValue()) + " (smoke v2)");
  await page.getByRole("button", { name: "Сохранить", exact: true }).click();
  await page
    .getByText("Изменения сохранены на сервере", { exact: true })
    .waitFor({ timeout: 20000 });
  await openDialog(page);
  const second = await evaluate(page);
  assert.notEqual(first.evaluationId, second.evaluationId);
  assert.ok(
    second.foundationChecklistVersion > first.foundationChecklistVersion,
  );
  assert.deepEqual(
    (await api(`/api/evaluations/${first.evaluationId}`)).result_json,
    original.result_json,
  );
  const history = await api("/api/history/browser-synthetic");
  assert.ok(history.some((h) => h.evaluationId === first.evaluationId));
  assert.ok(history.some((h) => h.evaluationId === second.evaluationId));
  report.checks.push(
    "edit criterion in UI -> new evaluation; old result/version preserved",
  );
  report.second = {
    evaluationId: second.evaluationId,
    score: second.score,
    seconds: second.measuredSeconds,
  };
  assert.deepEqual(errors, []);
  report.success = true;
} catch (error) {
  report.success = false;
  report.error = error.message;
  process.exitCode = 1;
} finally {
  await browser?.close();
  await stop();
  await writeFile(
    path.join(directory, "verification.json"),
    JSON.stringify(report, null, 2),
  );
  console.log(JSON.stringify({ directory, ...report }, null, 2));
}
