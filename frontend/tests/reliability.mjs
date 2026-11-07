// Browser regressions: evaluation honesty, startup recovery, appeal submission and phone imports.
// API responses are mocked; these checks do not measure model accuracy.
import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
import { conversations, initialCriteria } from "../src/data.js";

const baseUrl = process.env.BASE_URL || "http://127.0.0.1:5173";
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || "/usr/bin/chromium",
  args: ["--no-sandbox"],
});

function wavFixture() {
  const rate = 8000;
  const data = Buffer.alloc(44 + rate * 2);
  data.write("RIFF", 0);
  data.writeUInt32LE(36 + rate * 2, 4);
  data.write("WAVE", 8);
  data.write("fmt ", 12);
  data.writeUInt32LE(16, 16);
  data.writeUInt16LE(1, 20);
  data.writeUInt16LE(1, 22);
  data.writeUInt32LE(rate, 24);
  data.writeUInt32LE(rate * 2, 28);
  data.writeUInt16LE(2, 32);
  data.writeUInt16LE(16, 34);
  data.write("data", 36);
  data.writeUInt32LE(rate * 2, 40);
  for (let i = 0; i < rate; i++)
    data.writeInt16LE(
      Math.round(Math.sin((i * 2 * Math.PI * 440) / rate) * 12000),
      44 + i * 2,
    );
  return data;
}

async function makePage(workspace = null) {
  const page = await browser.newPage({
    viewport: { width: 1280, height: 900 },
  });
  await page.route("**/api/workspace", (route) =>
    route.fulfill({
      json:
        route.request().method() === "GET"
          ? { revision: workspace ? 1 : 0, data: workspace }
          : { revision: 2 },
    }),
  );
  await page.route("**/api/health", (route) =>
    route.fulfill({ json: { status: "model_unavailable" } }),
  );
  return page;
}

try {
  const partial = structuredClone(conversations[0]);
  partial.results = partial.results.slice(0, 1);
  partial.score = null;
  const partialPage = await makePage({
    dialogs: [partial],
    criteria: initialCriteria,
    version: 1,
    appeals: [],
  });
  await partialPage.goto(`${baseUrl}/#dialog/${partial.id}`);
  await partialPage
    .getByRole("heading", { name: "Анализ разговора", exact: true })
    .waitFor();
  await partialPage.getByText(/Рабочее пространство восстановлено/).waitFor();
  const missingRule = initialCriteria.find(
    (rule) => !partial.results.some((result) => result.criterionId === rule.id),
  );
  const missingRow = partialPage.getByRole("button", {
    name: `Критерий: ${missingRule.title}`,
    exact: true,
  });
  assert.equal(
    await missingRow.locator(".lucide-check").count(),
    0,
    "An absent result must not appear as a passed check",
  );
  assert.equal(
    await partialPage.getByText("Грубых ошибок нет", { exact: true }).count(),
    0,
    "An absent critical-error result must not imply no critical errors",
  );
  assert.equal(
    await partialPage.locator(".ca-score-ring strong").innerText(),
    "—",
  );
  await missingRow.click();
  assert.equal(
    await partialPage
      .getByRole("button", { name: "Оспорить оценку", exact: true })
      .count(),
    0,
    "There is no result to appeal for a missing criterion",
  );
  await partialPage.close();

  const criticalPartial = structuredClone(conversations[0]);
  criticalPartial.results = criticalPartial.results
    .filter((result) => String(result.criterionId) !== "2")
    .map((result) =>
      String(result.criterionId) === "8" ? { ...result, answer: "Да" } : result,
    );
  criticalPartial.score = null;
  const criticalPage = await makePage({
    dialogs: [criticalPartial],
    criteria: initialCriteria,
    version: 1,
    appeals: [],
  });
  await criticalPage.goto(`${baseUrl}/#dialog/${criticalPartial.id}`);
  await criticalPage.getByText(/Рабочее пространство восстановлено/).waitFor();
  assert.equal(
    await criticalPage.getByText("Грубая ошибка", { exact: true }).count(),
    1,
    "A known critical flag must remain visible even when another criterion is missing",
  );
  assert.equal(
    await criticalPage.locator(".ca-score-ring strong").innerText(),
    "—",
  );
  await criticalPage.close();

  const searchPage = await makePage();
  await searchPage.goto(`${baseUrl}/#dialog/${conversations[0].id}`);
  const searchInput = searchPage.getByLabel("Поиск по переписке", {
    exact: true,
  });
  await searchInput.pressSequentially("заяв", { delay: 70 });
  assert.equal(
    await searchInput.inputValue(),
    "заяв",
    "Typing a query must not lose focus after its first matching character",
  );
  assert.equal(
    await searchInput.evaluate((input) => document.activeElement === input),
    true,
  );
  const beforeMatch = await searchPage
    .locator(".message.highlighted")
    .getAttribute("id");
  await searchInput.press("Enter");
  assert.notEqual(
    await searchPage.locator(".message.highlighted").getAttribute("id"),
    beforeMatch,
    "Enter must navigate to the next matching message",
  );
  assert.equal(
    await searchInput.evaluate((input) => document.activeElement === input),
    true,
  );
  await searchPage
    .getByRole("button", { name: "Очистить поиск по переписке", exact: true })
    .click();
  assert.equal(await searchInput.inputValue(), "");
  await searchPage.close();

  const storagePage = await makePage();
  const errors = [];
  storagePage.on("pageerror", (error) => errors.push(error.message));
  await storagePage.addInitScript(() => {
    Storage.prototype.setItem = function () {
      throw new DOMException(
        "Browser storage is unavailable",
        "QuotaExceededError",
      );
    };
  });
  await storagePage.goto(baseUrl);
  await storagePage
    .getByRole("heading", {
      name: "Рабочее место контроля качества",
      exact: true,
    })
    .waitFor();
  await storagePage.locator(".desk-chat-row").first().click();
  await storagePage
    .getByRole("button", { name: "Открыть аналитику", exact: true })
    .click();
  await storagePage
    .getByRole("heading", { name: "Анализ разговора", exact: true })
    .waitFor();
  assert.equal(await storagePage.locator(".ca-criterion-row").count(), 8);
  assert.deepEqual(
    errors,
    [],
    "A storage write failure must not blank or crash the UI",
  );
  await storagePage.close();

  const corruptStoragePage = await makePage();
  await corruptStoragePage.addInitScript(() => {
    localStorage.setItem(
      "freedom-cqa-dialogs",
      JSON.stringify({ invalid: true }),
    );
    localStorage.setItem("freedom-cqa-criteria", JSON.stringify("invalid"));
    localStorage.setItem("freedom-cqa-appeals", JSON.stringify(null));
  });
  await corruptStoragePage.goto(baseUrl);
  await corruptStoragePage
    .getByRole("heading", {
      name: "Рабочее место контроля качества",
      exact: true,
    })
    .waitFor();
  assert.equal(await corruptStoragePage.locator(".desk-rule-row").count(), 8);
  assert.equal(
    await corruptStoragePage.locator(".desk-chat-row").count(),
    conversations.length,
  );
  await corruptStoragePage.close();

  // Plain HTTP hosts may not provide crypto.randomUUID; appeals must still work.
  const appealPage = await makePage();
  const appealErrors = [];
  appealPage.on("pageerror", (error) => appealErrors.push(error.message));
  await appealPage.addInitScript(() => {
    Object.defineProperty(globalThis.crypto, "randomUUID", {
      configurable: true,
      value: undefined,
    });
  });
  await appealPage.goto(`${baseUrl}/#dialog/${conversations[0].id}`);
  await appealPage
    .getByRole("button", {
      name: "Критерий: Установление контакта",
      exact: true,
    })
    .click();
  await appealPage
    .getByRole("button", { name: "Оспорить оценку", exact: true })
    .click();
  await appealPage
    .getByLabel("Причина апелляции")
    .fill("Проверка отправки без secure-context UUID.");
  await appealPage
    .getByRole("button", { name: "Отправить на пересмотр", exact: true })
    .evaluate((button) => {
      button.click();
      button.click();
    });
  await appealPage
    .getByRole("navigation")
    .getByRole("button", { name: "Апелляции" })
    .click();
  assert.equal(
    await appealPage.locator(".appeal-row").count(),
    1,
    "Repeated submit must not duplicate an appeal or crash the workspace",
  );
  await appealPage.reload();
  await appealPage
    .getByRole("button", { name: "Рассмотреть", exact: true })
    .waitFor();
  await appealPage
    .getByRole("button", { name: "Рассмотреть", exact: true })
    .click();
  await appealPage.getByLabel("Ответ после проверки").selectOption("Нет");
  await appealPage
    .getByLabel("Обоснование решения")
    .fill("Проверка завершена, интерфейс отвечает.");
  await appealPage
    .getByRole("button", { name: "Сохранить и пересчитать", exact: true })
    .click();
  await appealPage.getByText("Рассмотрена", { exact: true }).waitFor();
  assert.deepEqual(
    appealErrors,
    [],
    "The appeal lifecycle must remain responsive without randomUUID",
  );
  await appealPage.close();

  // Import a phone call through the organizer endpoint, preserving its actual transcript/audio metadata.
  const callPage = await makePage();
  const callId = "phone-browser-contract";
  const audioUrl = "https://audio.example.test/phone-browser-contract.wav";
  const secondCallId = "phone-browser-contract-second";
  const secondAudioUrl =
    "https://audio.example.test/phone-browser-contract-second.wav";
  await callPage.route("**/api/conversations/*/audio", (route) => {
    const bytes = wavFixture();
    const range = /bytes=(\d+)-(\d*)/.exec(
      route.request().headers().range || "",
    );
    const start = range ? Number(range[1]) : 0;
    const end =
      range && range[2]
        ? Math.min(Number(range[2]), bytes.length - 1)
        : bytes.length - 1;
    const body = bytes.subarray(start, end + 1);
    return route.fulfill({
      status: range ? 206 : 200,
      contentType: "audio/wav",
      body,
      headers: {
        "access-control-allow-origin": "*",
        "accept-ranges": "bytes",
        "content-length": String(body.length),
        ...(range
          ? { "content-range": `bytes ${start}-${end}/${bytes.length}` }
          : {}),
      },
    });
  });
  let releaseOrganizer;
  let requestedGroup;
  let evaluationPayload;
  const organizerStarted = new Promise((resolve) => {
    callPage.route("**/api/organizer?**", async (route) => {
      requestedGroup = new URL(route.request().url()).searchParams.get(
        "group_id",
      );
      resolve();
      await new Promise((release) => {
        releaseOrganizer = release;
      });
      await route.fulfill({
        json: {
          isSuccess: true,
          data: {
            records: [
              {
                conversation_id: callId,
                channel: "voice call",
                language: "RU",
                audio_url: audioUrl,
                transcript: [
                  {
                    speaker: "client",
                    timestamp: "2026-11-07T12:42:01+00:00",
                    text: "Здравствуйте, уточните комиссию по счёту.",
                  },
                  {
                    speaker: "operator",
                    timestamp: "2026-11-07T12:42:04+00:00",
                    text: "Здравствуйте, я оператор. Уточню тариф и помогу.",
                  },
                ],
              },
              {
                conversation_id: secondCallId,
                channel: "voice call",
                language: "RU",
                audio_url: secondAudioUrl,
                transcript: [
                  {
                    speaker: "client",
                    timestamp: "00:01",
                    text: "Проверка второго звонка.",
                  },
                  {
                    speaker: "operator",
                    timestamp: "00:02",
                    text: "Здравствуйте, помогу со вторым обращением.",
                  },
                ],
              },
            ],
          },
        },
      });
    });
  });
  await callPage.route("**/api/evaluate*", async (route) => {
    evaluationPayload = route.request().postDataJSON();
    const evidence = evaluationPayload.messages.find(
      (message) => message.role === "operator",
    );
    await route.fulfill({
      json: {
        evaluationId: "phone-contract",
        model: "phone-contract-model",
        passes: 2,
        tokens: 20,
        checklistVersion: evaluationPayload.version,
        criteriaSnapshot: evaluationPayload.criteria,
        score: 100,
        critical: false,
        results: evaluationPayload.criteria.map((criterion) => ({
          criterionId: criterion.id,
          answer:
            criterion.type === "flag"
              ? "Нет"
              : criterion.naAllowed
                ? "N/A"
                : criterion.type === "scale"
                  ? Math.max(...criterion.scale)
                  : "Да",
          reason:
            "Mocked UI contract result, not a real model accuracy measurement.",
          evidenceId: evidence.id,
          quote: evidence.text,
          checkedMessageIds: [evidence.id],
          confidence: 0.8,
        })),
      },
    });
  });
  await callPage.goto(baseUrl);
  await callPage
    .getByRole("button", { name: "Загрузить диалоги", exact: true })
    .click();
  await callPage.getByLabel("Группа данных", { exact: true }).fill("DEV");
  await callPage
    .getByRole("button", { name: "Получить данные организаторов", exact: true })
    .click();
  await organizerStarted;
  assert.equal(
    await callPage
      .getByRole("button", { name: "Получаем чаты и звонки…", exact: true })
      .isDisabled(),
    true,
  );
  releaseOrganizer();
  await callPage.getByText(/Получено: 2 · чаты: 0 · звонки: 2/).waitFor();
  assert.equal(requestedGroup, "DEV");
  await callPage
    .getByRole("button", { name: "Импортировать", exact: true })
    .click();
  await callPage
    .getByRole("button", { name: `Выбрать диалог ${callId}`, exact: true })
    .click();
  await callPage
    .getByRole("button", { name: "Открыть аналитику", exact: true })
    .click();
  assert.match(
    await callPage.locator(".ca-heading").innerText(),
    /Телефонный разговор/,
  );
  assert.match(await callPage.locator(".ca-heading").innerText(), /Звонок/);
  assert.equal(
    await callPage.locator(".ca-message time").first().innerText(),
    "12:42:01",
  );
  assert.equal(
    await callPage.locator(".ca-message time").first().getAttribute("datetime"),
    "2026-11-07T12:42:01+00:00",
  );
  assert.equal(
    await callPage.locator(".ca-score-ring strong").innerText(),
    "—",
  );
  const recording = callPage.locator("audio");
  assert.equal(
    await recording.count(),
    1,
    "A call must have one actual recording player",
  );
  assert.equal(
    await recording.isVisible(),
    true,
    "The recording must be visible without expanding chronology",
  );
  assert.equal(
    await recording.getAttribute("src"),
    `/api/conversations/${callId}/audio`,
  );
  await recording.evaluate(async (audio) => {
    audio.muted = true;
    await audio.play();
  });
  await callPage.waitForFunction(() => {
    const audio = document.querySelector("audio");
    return audio && audio.currentTime > 0.05;
  });
  assert.ok(
    await recording.evaluate((audio) => audio.duration >= 0.9),
    "The native player must decode the real WAV fixture",
  );
  await recording.evaluate((audio) => {
    audio.pause();
    audio.currentTime = 0.4;
  });
  assert.ok(await recording.evaluate((audio) => audio.currentTime >= 0.35));
  await callPage
    .getByRole("button", { name: "Показать звуковую дорожку", exact: true })
    .click();
  const waveform = callPage.getByRole("slider", {
    name: "Позиция в аудиозаписи",
    exact: true,
  });
  await waveform.waitFor();
  assert.ok(
    (await waveform.locator("rect").count()) > 0,
    "A waveform must come from decoded WAV samples",
  );
  await waveform.press("Home");
  assert.ok(await recording.evaluate((audio) => audio.currentTime < 0.05));
  await waveform.press("End");
  assert.ok(await recording.evaluate((audio) => audio.currentTime >= 0.9));
  await callPage
    .getByText("Оценивание и история запусков", { exact: true })
    .click();
  await callPage
    .getByRole("button", { name: "Оценить диалог", exact: true })
    .click();
  await callPage.getByText(/AI: phone-contract-model/).waitFor();
  assert.equal(evaluationPayload.conversation_id, callId);
  assert.equal(evaluationPayload.messages.length, 2);
  assert.equal(evaluationPayload.messages[0].time, "2026-11-07T12:42:01+00:00");
  assert.equal(evaluationPayload.messages[1].role, "operator");
  assert.equal(evaluationPayload.criteria.length, 8);
  assert.equal(
    await callPage.locator(".ca-score-ring strong").innerText(),
    "100",
  );
  await callPage
    .getByRole("button", { name: "Показать реплику", exact: true })
    .click();
  assert.match(
    await callPage.locator(".message.highlighted").innerText(),
    /Уточню тариф/,
  );
  await callPage.getByLabel("Выбрать другой диалог").selectOption(secondCallId);
  const secondRecording = callPage.locator("audio");
  assert.equal(
    await secondRecording.getAttribute("src"),
    `/api/conversations/${secondCallId}/audio`,
  );
  assert.equal(
    await secondRecording.evaluate(
      (audio) => audio.paused && audio.currentTime === 0,
    ),
    true,
    "Switching a call must reset the previous recording position and playback",
  );
  await callPage.waitForFunction(
    () => document.querySelector("audio")?.duration > 0,
  );
  await callPage.route(
    `**/api/conversations/${secondCallId}/audio`,
    (route) => {
      const bytes = wavFixture();
      return route.fulfill({
        status: 206,
        contentType: "audio/wav",
        body: bytes,
        headers: {
          "content-range": `bytes 0-${bytes.length - 1}/${bytes.length + 1000}`,
        },
      });
    },
  );
  await callPage
    .getByRole("button", { name: "Показать звуковую дорожку", exact: true })
    .click();
  await callPage.getByText(/Источник передал только часть записи/).waitFor();
  assert.equal(
    await callPage
      .getByRole("slider", { name: "Позиция в аудиозаписи", exact: true })
      .count(),
    0,
    "A partial media response must not create a misleading complete waveform",
  );
  const noAudioCall = conversations.find(
    (dialog) => dialog.channel === "call" && !dialog.audio_url,
  );
  assert.ok(noAudioCall);
  await callPage
    .getByLabel("Выбрать другой диалог")
    .selectOption(noAudioCall.id);
  assert.equal(
    await callPage.locator("audio").count(),
    0,
    "No recording URL must not produce a fake player",
  );
  await callPage
    .getByRole("navigation")
    .getByRole("button", { name: "Диалоги" })
    .click();
  await callPage
    .getByRole("button", { name: "Загрузить диалоги", exact: true })
    .click();
  await callPage.getByLabel("Ответ API", { exact: true }).fill(
    JSON.stringify({
      data: {
        records: [
          {
            conversation_id: 123,
            channel: "agent chat",
            language: "RU",
            transcript: [
              {
                speaker: "client",
                timestamp: "00:01",
                text: "Invalid identifier contract case.",
              },
            ],
          },
        ],
      },
    }),
  );
  await callPage
    .getByRole("button", { name: "Импортировать", exact: true })
    .click();
  await callPage.getByRole("alert").filter({ hasText: "Запись 1" }).waitFor();
  assert.equal(
    await callPage.getByRole("dialog").isVisible(),
    true,
    "An invalid numeric identifier must show a form error rather than crashing the workspace",
  );
  await callPage.keyboard.press("Escape");
  await callPage
    .getByRole("heading", {
      name: "Рабочее место контроля качества",
      exact: true,
    })
    .waitFor();
  await callPage.close();

  const failedBootPage = await makePage();
  await failedBootPage.route(
    /\/(?:src\/main\.jsx|assets\/[^/]+\.js)(?:\?.*)?$/,
    (route) => route.abort(),
  );
  await failedBootPage.goto(baseUrl);
  await failedBootPage
    .getByRole("heading", {
      name: "Не удалось загрузить приложение",
      exact: true,
    })
    .waitFor({ timeout: 10000 });
  assert.equal(
    await failedBootPage.locator("#boot-screen").getAttribute("role"),
    "alert",
  );
  assert.equal(
    await failedBootPage.locator("#boot-instructions").isVisible(),
    true,
    "A failed JS module must show recovery instructions instead of an empty page",
  );
  await failedBootPage.close();

  console.log(
    "PASS: incomplete/critical results, storage recovery, keyboard search, appeal without randomUUID, double submit, organizer phone import/audio/evaluation/evidence and failed-JS recovery. API mocked.",
  );
} finally {
  await browser.close();
}
