import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  initialCriteria,
  conversations,
  scoreEvaluation,
} from "../src/data.js";

const base = conversations.find((d) => d.status !== "pending");
const perfect = initialCriteria.map((c) => ({
  criterionId: c.id,
  answer:
    c.type === "scale"
      ? Math.max(...c.scale)
      : c.type === "flag"
        ? "Нет"
        : "Да",
}));
assert.equal(scoreEvaluation(initialCriteria, perfect).score, 100);
assert.equal(
  scoreEvaluation(
    initialCriteria,
    perfect.map((r) => (r.criterionId === "6" ? { ...r, answer: 7 } : r)),
  ).score,
  95.5,
);
assert.deepEqual(
  scoreEvaluation(
    initialCriteria,
    perfect.map((r) => (r.criterionId === "8" ? { ...r, answer: "Да" } : r)),
  ),
  { score: 100, critical: true },
);
assert.equal(
  scoreEvaluation(
    initialCriteria,
    perfect.map((r) => (r.criterionId === "3" ? { ...r, answer: "N/A" } : r)),
  ).score,
  100,
);
assert.equal(scoreEvaluation(initialCriteria, perfect.slice(1)).score, null);

const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || "/usr/bin/chromium",
  args: ["--no-sandbox"],
});
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1100 },
    reducedMotion: "reduce",
  });
  await page.route("**/api/workspace", (route) =>
    route.fulfill({ json: { revision: 0, data: null } }),
  );
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(process.env.BASE_URL || "http://127.0.0.1:5173");
  await page
    .getByRole("heading", {
      name: "Рабочее место контроля качества",
      exact: true,
    })
    .waitFor();
  assert.equal(await page.locator(".desk-rule-row").count(), 8);
  assert.equal(
    await page.locator(".desk-chat-row").count(),
    conversations.length,
  );
  assert.equal(
    await page
      .getByRole("button", { name: "Открыть аналитику", exact: true })
      .isDisabled(),
    true,
  );
  assert.match(await page.locator(".desk-average").innerText(), /92,36/);
  await page.getByLabel("Язык", { exact: true }).selectOption("KZ");
  assert.equal(
    await page.locator(".desk-chat-row").count(),
    conversations.filter((d) => d.language === "KZ").length,
  );
  await page.getByLabel("Язык", { exact: true }).selectOption("all");
  await page
    .getByLabel("Поиск диалогов", { exact: true })
    .fill("no-such-conversation");
  await page.getByText("Диалоги не найдены", { exact: true }).waitFor();
  await page
    .getByRole("button", { name: "Сбросить фильтры", exact: true })
    .click();
  await page.getByLabel("Поиск диалогов", { exact: true }).fill(base.id);
  await page
    .getByRole("button", { name: `Выбрать диалог ${base.id}`, exact: true })
    .click();
  assert.equal(await page.locator(".ca-analysis").count(), 0);
  assert.match(await page.locator(".desk-selected-score").innerText(), /81,88/);
  assert.equal(
    await page
      .getByRole("button", { name: "Открыть аналитику", exact: true })
      .isEnabled(),
    true,
  );
  await page
    .getByRole("button", {
      name: "Настроить критерий: Установление контакта",
      exact: true,
    })
    .click();
  await page
    .getByLabel("Название", { exact: true })
    .fill("Контакт и приветствие");
  await page.getByRole("button", { name: "Сохранить", exact: true }).click();
  assert.match(await page.locator(".desk-rules").innerText(), /Версия 2/);
  assert.match(
    await page.locator(".desk-selected-criteria").innerText(),
    /Установление контакта/,
  );
  await page
    .getByRole("button", { name: "Открыть аналитику", exact: true })
    .click();
  await page
    .getByRole("heading", { name: "Анализ разговора", exact: true })
    .waitFor();
  assert.match(
    await page.locator(".ca-heading").innerText(),
    new RegExp(base.id),
  );
  assert.ok(page.url().endsWith("#dialog/" + base.id));
  assert.match(
    await page.locator(".ca-score-ring").getAttribute("aria-label"),
    /81,88/,
  );
  await page.getByRole("button", { name: "Реплика #m7", exact: true }).click();
  assert.ok(await page.locator(".message.highlighted").isVisible());
  await page.getByLabel("Поиск по переписке").fill("заявка");
  assert.ok((await page.locator(".ca-message mark").count()) > 0);
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Отчёт", exact: true }).click();
  const exported = JSON.parse(
    await readFile(await (await downloadEvent).path(), "utf8"),
  );
  assert.equal(exported.conversations.length, 1);
  assert.equal(exported.conversations[0].id, base.id);
  assert.equal(await page.locator(".ca-criterion-row").count(), 8);
  await page
    .getByRole("button", {
      name: "Критерий: Установление контакта",
      exact: true,
    })
    .click();
  await page
    .getByRole("button", { name: "Оспорить оценку", exact: true })
    .click();
  assert.match(
    await page.locator(".appeal-context").innerText(),
    /Установление контакта/,
  );
  await page
    .getByLabel("Причина апелляции")
    .fill("Прошу повторно проверить приветствие оператора.");
  await page
    .getByRole("button", { name: "Отправить на пересмотр", exact: true })
    .click();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Апелляции" })
    .click();
  await page.getByRole("button", { name: "Рассмотреть" }).click();
  assert.match(
    await page.locator(".appeal-context").innerText(),
    /Здравствуйте/,
  );
  await page.getByLabel("Ответ после проверки").selectOption("Нет");
  await page
    .getByLabel("Обоснование решения")
    .fill("Тестовый пересмотр по исходной реплике.");
  await page.getByRole("button", { name: "Сохранить и пересчитать" }).click();
  await page.getByText("Рассмотрена", { exact: true }).waitFor();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Диалоги" })
    .click();
  await page
    .getByRole("button", { name: `Выбрать диалог ${base.id}`, exact: true })
    .click();
  assert.match(await page.locator(".desk-selected-score").innerText(), /69,38/);
  await page.getByRole("button", { name: "Загрузить диалоги" }).click();
  await page.getByLabel("Ответ API", { exact: true }).fill(
    JSON.stringify({
      data: {
        records: [
          {
            conversation_id: "import-smoke",
            channel: "agent chat",
            language: "RU",
            transcript: [
              {
                timestamp: "00:01",
                speaker: "client",
                text: "Здравствуйте!",
              },
            ],
            audio_url: null,
          },
        ],
      },
    }),
  );
  await page
    .getByRole("button", { name: "Импортировать", exact: true })
    .click();
  await page.getByLabel("Поиск диалогов", { exact: true }).fill("import-smoke");
  await page
    .getByRole("button", { name: "Выбрать диалог import-smoke", exact: true })
    .click();
  await page.getByText("Диалог ожидает оценки", { exact: true }).waitFor();
  await page
    .getByRole("button", { name: "Открыть аналитику", exact: true })
    .click();
  assert.equal(
    await page.locator(".ca-score-ring").getAttribute("aria-label"),
    "Итоговый балл ещё не рассчитан",
  );
  await page.reload();
  await page
    .getByRole("heading", { name: "Анализ разговора", exact: true })
    .waitFor();
  assert.match(await page.locator(".ca-heading").innerText(), /import-smoke/);
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Критерии оценки" })
    .click();
  await page.getByRole("button", { name: "Добавить критерий" }).click();
  await page.keyboard.press("Escape");
  assert.equal(await page.getByRole("dialog").count(), 0);
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Диалоги" })
    .click();
  await page.setViewportSize({ width: 1280, height: 900 });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    ),
    false,
  );
  assert.deepEqual(errors, []);
  console.log(
    "PASS: desktop sketch layout, selection gate, search/filtering, true statistics, versioned criteria, per-dialogue review/evidence/report, contextual appeal and recalculation, pending import, deep links and Escape.",
  );
} finally {
  await browser.close();
}
