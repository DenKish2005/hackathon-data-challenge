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
    viewport: { width: 1440, height: 1000 },
  });
  await page.route("**/api/workspace", (route) =>
    route.fulfill({ json: { revision: 0, data: null } }),
  );
  const errors = [];
  await page.emulateMedia({ reducedMotion: "reduce" });
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(process.env.BASE_URL || "http://127.0.0.1:5173");
  await page.getByRole("heading", { name: "Диалоги", exact: true }).waitFor();
  assert.equal(await page.locator(".rw-workspace").count(), 0);
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Общая статистика", exact: true })
    .click();
  await page
    .getByRole("heading", { name: "Обзор качества", exact: true })
    .waitFor();
  assert.match(await page.title(), /Freedom Broker/);
  assert.doesNotMatch(await page.locator("body").innerText(), /Sana|Сана/i);
  await page.getByLabel("Период аналитики").selectOption("Все оценки");
  assert.equal(
    await page.locator('svg [role="button"]').count(),
    conversations.filter((d) => d.status !== "pending").length,
  );
  await page.getByLabel("Период аналитики").selectOption("Последние 7 оценок");
  assert.equal(await page.locator('svg [role="button"]').count(), 7);
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Диалоги" })
    .click();
  await page.getByLabel("Язык", { exact: true }).selectOption("KZ");
  assert.ok((await page.locator("tbody tr").count()) > 0);
  for (const row of await page.locator("tbody tr").all())
    assert.match(await row.innerText(), /KZ/);
  await page.getByLabel("Язык", { exact: true }).selectOption("Все языки");
  await page.getByLabel("Сортировка").selectOption("low");
  const sortedScores = await page
    .locator("tbody tr .score")
    .evaluateAll((nodes) =>
      nodes.map((n) => Number(n.childNodes[0].textContent)),
    );
  assert.deepEqual(
    sortedScores,
    [...sortedScores].sort((a, b) => a - b),
  );
  await page
    .getByRole("group", { name: "Очередь диалогов" })
    .getByRole("button", { name: /Грубые ошибки/ })
    .click();
  assert.equal(await page.locator("tbody tr").count(), 1);
  assert.equal(await page.locator("tbody .critical-indicator").count(), 1);
  await page
    .getByRole("group", { name: "Очередь диалогов" })
    .getByRole("button", { name: /Все диалоги/ })
    .click();
  await page.getByLabel("Сортировка").selectOption("recent");

  await page.getByLabel("Поиск диалогов").fill(base.id);
  await page.locator("tbody .dialog-button").first().click();
  await page.getByRole("heading", { name: "Транскрипт" }).waitFor();
  await page.getByRole("heading", { name: base.topic, exact: true }).waitFor();
  assert.equal(await page.locator(".rw-workspace").count(), 1);
  assert.ok(page.url().endsWith("#dialog/" + base.id));
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Отчёт", exact: true }).click();
  const exported = JSON.parse(
    await readFile(await (await downloadEvent).path(), "utf8"),
  );
  assert.equal(exported.conversations.length, 1);
  assert.equal(exported.conversations[0].id, base.id);

  const other = conversations.find(
    (d) => d.id !== base.id && d.status !== "pending",
  );
  await page.getByLabel("Выбрать другой диалог").selectOption(other.id);
  assert.ok(page.url().endsWith("#dialog/" + other.id));
  assert.match(
    await page.locator(".rw-overall-score").getAttribute("aria-label"),
    new RegExp(String(other.score).replace(".", ",")),
  );
  await page.getByLabel("Выбрать другой диалог").selectOption(base.id);
  await page.reload();
  await page.getByRole("heading", { name: base.topic, exact: true }).waitFor();
  assert.ok(page.url().endsWith("#dialog/" + base.id));
  await page
    .getByRole("group", { name: "Фильтр критериев" })
    .getByRole("button", { name: /Замечания/ })
    .click();
  assert.equal(await page.locator(".rw-criterion").count(), 2);
  await page
    .getByRole("group", { name: "Фильтр критериев" })
    .getByRole("button", { name: /Все/ })
    .click();
  const contact = page
    .locator(".rw-criterion-toggle")
    .filter({ hasText: "Установление контакта" });
  if ((await contact.getAttribute("aria-expanded")) !== "true")
    await contact.click();
  await page
    .getByRole("button", {
      name: "Реплика #" + base.results[0].evidenceId,
      exact: true,
    })
    .first()
    .click();
  assert.ok((await page.locator(".message.highlighted").count()) > 0);
  await page
    .locator(".criteria-results")
    .getByRole("button", { name: "Оспорить", exact: true })
    .first()
    .click();
  await page.locator(".appeal-context").waitFor();
  assert.match(
    await page.locator(".appeal-context").innerText(),
    /Установление контакта/,
  );
  await page
    .getByLabel("Причина апелляции")
    .fill("Прошу проверить приветствие по первой реплике оператора.");
  await page.getByRole("button", { name: "Отправить на пересмотр" }).click();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Апелляции" })
    .click();
  await page.getByRole("button", { name: "Рассмотреть" }).click();
  await page.getByLabel("Ответ после проверки").selectOption("Нет");
  await page
    .getByLabel("Обоснование решения")
    .fill("Тестовый пересмотр: приветствие не соответствует правилу.");
  await page.getByRole("button", { name: "Сохранить и пересчитать" }).click();
  assert.equal(await page.getByText("Рассмотрена", { exact: true }).count(), 1);
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Критерии оценки" })
    .click();
  await page
    .getByRole("button", { name: "Настроить", exact: true })
    .first()
    .click();
  await page
    .getByLabel("Название", { exact: true })
    .fill("Контакт и приветствие");
  await page.getByRole("button", { name: "Сохранить", exact: true }).click();
  assert.equal(
    await page
      .getByRole("heading", { name: "Контакт и приветствие", exact: true })
      .count(),
    1,
  );
  await page.reload();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Критерии оценки" })
    .click();
  assert.equal(
    await page
      .getByRole("heading", { name: "Контакт и приветствие", exact: true })
      .count(),
    1,
  );
  await page.getByRole("button", { name: "Добавить критерий" }).click();
  await page.keyboard.press("Escape");
  assert.equal(await page.getByRole("dialog").count(), 0);
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Диалоги" })
    .click();
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
  await page.getByLabel("Поиск диалогов").fill("import-smoke");
  assert.equal(await page.locator("tbody tr").count(), 1);
  await page.locator("tbody .dialog-button").first().click();
  await page.getByRole("heading", { name: "Ожидает оценки" }).first().waitFor();
  assert.equal(
    await page.locator(".rw-overall-score").getAttribute("aria-label"),
    "Итоговый балл ещё не рассчитан",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Открыть меню" }).click();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Диалоги" })
    .click();
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    ),
    false,
  );
  const criticalTab = page
    .getByRole("group", { name: "Очередь диалогов" })
    .getByRole("button", { name: /Грубые ошибки/ });
  const tabBox = await criticalTab.boundingBox();
  assert.ok(tabBox.x >= 0 && tabBox.x + tabBox.width <= 390);
  const mobileCard = page.getByRole("button", {
    name: `Открыть диалог ${base.id}: ${base.topic}`,
  });
  assert.ok(await mobileCard.isVisible());
  const box = await mobileCard.boundingBox();
  assert.ok(box.x >= 0 && box.x + box.width <= 390);
  await mobileCard.click();
  await page.getByRole("tab", { name: /Оценка/ }).click();
  const consultation = page
    .locator(".rw-criterion-toggle")
    .filter({ hasText: "Корректная и полная консультация" });
  if ((await consultation.getAttribute("aria-expanded")) !== "true")
    await consultation.click();
  const evidenceButton = page.getByRole("button", {
    name: "Реплика #m7",
    exact: true,
  });
  await evidenceButton.click();
  assert.equal(
    await page
      .getByRole("tab", { name: /Переписка/ })
      .getAttribute("aria-selected"),
    "true",
  );
  assert.ok(await page.locator(".message.highlighted").isVisible());
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    ),
    false,
  );
  await page.getByLabel("Поиск по переписке").fill("заявка");
  assert.ok((await page.locator(".rw-message mark").count()) > 0);
  await page.screenshot({
    path: "/tmp/freedom-dark-mobile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 1050 });
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await page.screenshot({ path: "/tmp/freedom-desktop.png", fullPage: true });
  assert.deepEqual(errors, []);
  console.log(
    "PASS: scoring, sorting, queue filters, selected report, criterion filters, linked evidence, contextual appeal and recalculation, versioned checklist, import, keyboard modal, mobile queue and review tabs.",
  );
} finally {
  await browser.close();
}
