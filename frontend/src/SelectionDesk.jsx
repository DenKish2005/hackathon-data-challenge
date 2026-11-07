import React, { useMemo, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Headphones,
  MessageCircle,
  Search,
  ShieldAlert,
  SlidersHorizontal,
} from "lucide-react";
import { initialCriteria, scoreEvaluation } from "./data";

const format = (value) =>
  typeof value === "number"
    ? value.toLocaleString("ru-RU", { maximumFractionDigits: 2 })
    : "—";

function evaluation(dialog) {
  if (!dialog || dialog.status === "pending" || !dialog.results?.length)
    return { score: null, critical: false, ready: false };
  const result = scoreEvaluation(
    dialog.criteriaSnapshot || initialCriteria,
    dialog.results,
  );
  return { ...result, ready: !result.incomplete && result.score !== null };
}

function isIssue(rule, result) {
  if (!result || result.answer === "N/A") return false;
  if (rule.type === "flag") return result.answer === "Да";
  if (rule.type === "scale")
    return (
      typeof result.answer === "number" &&
      result.answer < Math.max(...rule.scale)
    );
  return result.answer === "Нет";
}

function answerLabel(rule, result) {
  if (!result) return "Не оценён";
  return rule.type === "scale" && typeof result.answer === "number"
    ? `${result.answer} / ${Math.max(...rule.scale)}`
    : result.answer;
}

function DeskStatus({ status }) {
  const label =
    status === "pending"
      ? "Без оценки"
      : status === "review"
        ? "На проверке"
        : "Оценён";
  return (
    <span className={`desk-status desk-status-${status}`}>
      <span />
      {label}
    </span>
  );
}

export default function SelectionDesk({
  dialogs,
  initialCandidateId = null,
  criteria,
  version,
  onOpen,
  onEditCriterion,
  onChecklist,
  onAppeal,
}) {
  const [candidateId, setCandidateId] = useState(initialCandidateId);
  const [query, setQuery] = useState("");
  const [language, setLanguage] = useState("all");
  const [channel, setChannel] = useState("all");
  const candidate = dialogs.find((dialog) => dialog.id === candidateId) || null;
  const current = evaluation(candidate);
  const snapshot = candidate?.criteriaSnapshot || initialCriteria;
  const currentResults = candidate?.results || [];
  const findings = current.ready
    ? snapshot.flatMap((rule) => {
        const result = currentResults.find(
          (item) => String(item.criterionId) === String(rule.id),
        );
        return isIssue(rule, result) ? [{ rule, result }] : [];
      })
    : [];
  const applicable = snapshot.filter((rule) => {
    const result = currentResults.find(
      (item) => String(item.criterionId) === String(rule.id),
    );
    return (
      rule.type !== "flag" &&
      Number(rule.weight) > 0 &&
      result &&
      result.answer !== "N/A"
    );
  }).length;
  const naCount = currentResults.filter(
    (result) => result.answer === "N/A",
  ).length;

  const visible = useMemo(() => {
    const term = query.trim().toLocaleLowerCase();
    return dialogs.filter(
      (dialog) =>
        (language === "all" || dialog.language === language) &&
        (channel === "all" || dialog.channel === channel) &&
        `${dialog.id} ${dialog.topic} ${dialog.customer} ${dialog.agent}`
          .toLocaleLowerCase()
          .includes(term),
    );
  }, [dialogs, query, language, channel]);

  const assessed = dialogs
    .map((dialog) => ({
      dialog,
      calculation: evaluation(dialog),
    }))
    .filter(({ calculation }) => calculation.ready);
  const average = assessed.length
    ? assessed.reduce((sum, item) => sum + item.calculation.score, 0) /
      assessed.length
    : null;
  const needsReview = dialogs.filter(
    (dialog) => dialog.status === "review",
  ).length;
  const pending = dialogs.filter(
    (dialog) => dialog.status === "pending",
  ).length;
  const critical = assessed.filter((item) => item.calculation.critical).length;
  const bars = [
    { label: "Всего диалогов", value: dialogs.length, tone: "total" },
    { label: "Оценено", value: assessed.length, tone: "assessed" },
    { label: "На проверке", value: needsReview, tone: "review" },
    { label: "Без оценки", value: pending, tone: "pending" },
  ];
  const max = Math.max(1, ...bars.map((bar) => bar.value));

  function resetFilters() {
    setQuery("");
    setLanguage("all");
    setChannel("all");
  }

  return (
    <div className="selection-desk">
      <div className="desk-top-grid">
        <section className="desk-panel desk-rules" aria-label="Критерии оценки">
          <header className="desk-panel-heading">
            <div>
              <span className="desk-section-index">01</span>
              <h2>Критерии оценки</h2>
            </div>
            <span className="desk-version">Версия {version}</span>
          </header>
          <p className="desk-panel-caption">
            Единый стандарт качества для всех диалогов
          </p>
          <div className="desk-rule-list">
            {criteria.map((rule, index) => (
              <button
                className="desk-rule-row"
                key={rule.id}
                onClick={() => onEditCriterion?.(rule)}
                aria-label={`Настроить критерий: ${rule.title}`}
              >
                <span className="desk-rule-number">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="desk-rule-title">{rule.title}</span>
                <span className="desk-rule-weight">
                  {rule.type === "flag" ? "Флаг" : `${rule.weight} б.`}
                </span>
                <ChevronRight size={13} />
              </button>
            ))}
          </div>
          <footer className="desk-rules-footer">
            <span>{criteria.length} критериев · RU / KZ / EN</span>
            <button onClick={onChecklist}>
              <SlidersHorizontal size={13} /> Настроить чек-лист
            </button>
          </footer>
        </section>

        <section className="desk-panel desk-chats" aria-label="Выбор диалога">
          <header className="desk-panel-heading">
            <div>
              <span className="desk-section-index">02</span>
              <h2>Выберите диалог</h2>
              <span className="desk-total-count">{dialogs.length}</span>
            </div>
            <span className="desk-source">Демонстрационный набор</span>
          </header>
          <div className="desk-chat-toolbar">
            <label className="desk-search">
              <Search size={15} />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Найти по теме, клиенту или ID"
                aria-label="Поиск диалогов"
              />
            </label>
            <select
              aria-label="Язык"
              value={language}
              onChange={(event) => setLanguage(event.target.value)}
            >
              <option value="all">Все языки</option>
              <option value="RU">RU</option>
              <option value="KZ">KZ</option>
              <option value="EN">EN</option>
            </select>
            <select
              aria-label="Канал"
              value={channel}
              onChange={(event) => setChannel(event.target.value)}
            >
              <option value="all">Все каналы</option>
              <option value="chat">Чаты</option>
              <option value="call">Звонки</option>
            </select>
          </div>
          <div
            className="desk-chat-list"
            role="group"
            aria-label="Список диалогов"
          >
            {visible.map((dialog) => {
              const chosen = dialog.id === candidateId;
              const score = evaluation(dialog);
              const ChannelIcon =
                dialog.channel === "call" ? Headphones : MessageCircle;
              return (
                <button
                  className={`desk-chat-row ${chosen ? "is-selected" : ""}`}
                  key={dialog.id}
                  aria-label={`Выбрать диалог ${dialog.id}`}
                  aria-pressed={chosen}
                  onClick={() => setCandidateId(dialog.id)}
                >
                  <span className="desk-choice-indicator">
                    {chosen ? <Check size={12} /> : null}
                  </span>
                  <span className="desk-channel-icon">
                    <ChannelIcon size={16} />
                  </span>
                  <span className="desk-chat-copy">
                    <strong>{dialog.topic}</strong>
                    <small>
                      {dialog.id} <span>·</span> {dialog.customer}
                    </small>
                  </span>
                  <span className="desk-chat-language">{dialog.language}</span>
                  <span
                    className={`desk-chat-score ${score.critical ? "is-critical" : ""}`}
                  >
                    {score.critical && <ShieldAlert size={13} />}
                    {format(score.score)}
                    <small>/100</small>
                  </span>
                  <DeskStatus status={dialog.status} />
                </button>
              );
            })}
            {!visible.length && (
              <div className="desk-empty-search">
                <Search size={23} />
                <strong>Диалоги не найдены</strong>
                <p>Попробуйте другую тему, ID или язык.</p>
                <button onClick={resetFilters}>Сбросить фильтры</button>
              </div>
            )}
          </div>
          <footer className="desk-chat-footer">
            <span>
              {candidate ? (
                <>
                  Выбран <strong>{candidate.id}</strong>
                </>
              ) : (
                "Выберите один диалог для подробного разбора"
              )}
            </span>
            <button
              className="desk-primary-button"
              disabled={!candidate}
              onClick={() => candidate && onOpen(candidate)}
            >
              Открыть аналитику <ArrowRight size={15} />
            </button>
          </footer>
        </section>
      </div>

      <section
        className="desk-panel desk-statistics"
        aria-label="Общая статистика"
      >
        <header className="desk-panel-heading">
          <div>
            <span className="desk-section-index">03</span>
            <h2>Общая статистика</h2>
          </div>
          <span className="desk-source">По текущему набору диалогов</span>
        </header>
        <div className="desk-statistics-content">
          <div
            className="desk-bar-chart"
            role="img"
            aria-label={bars
              .map((bar) => `${bar.label}: ${bar.value}`)
              .join("; ")}
          >
            <div className="desk-chart-grid" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
            {bars.map((bar) => (
              <div
                className={`desk-bar-column desk-bar-${bar.tone}`}
                key={bar.label}
              >
                <span className="desk-bar-value">{bar.value}</span>
                <div className="desk-bar-track">
                  <span style={{ height: `${(bar.value / max) * 100}%` }} />
                </div>
                <span className="desk-bar-label">{bar.label}</span>
              </div>
            ))}
          </div>
          <div className="desk-average">
            <span className="desk-metric-label">Средняя оценка качества</span>
            <strong>
              {format(average)}
              <small>/100</small>
            </strong>
            <p>
              {assessed.length
                ? `На основе ${assessed.length} завершённых оценок`
                : "Пока нет завершённых оценок"}
            </p>
            <div className="desk-average-scale">
              <span style={{ width: `${average || 0}%` }} />
            </div>
          </div>
          <div className="desk-critical-summary">
            <span
              className={`desk-summary-icon ${critical ? "has-critical" : ""}`}
            >
              {critical ? (
                <ShieldAlert size={21} />
              ) : (
                <CheckCircle2 size={21} />
              )}
            </span>
            <strong>{critical}</strong>
            <span>диалогов с грубыми ошибками</span>
            <small>Отдельный флаг, без обнуления оценки</small>
          </div>
        </div>
      </section>

      <section
        className={`desk-panel desk-selected ${candidate ? "has-selection" : ""}`}
        aria-label="Статистика выбранного диалога"
      >
        <header className="desk-panel-heading">
          <div>
            <span className="desk-section-index">04</span>
            <h2>Статистика выбранного диалога</h2>
          </div>
          {candidate && (
            <span className="desk-selected-id">
              {candidate.id} <span>·</span> {candidate.topic}
            </span>
          )}
        </header>
        {!candidate ? (
          <div className="desk-selection-placeholder">
            <MessageCircle size={23} />
            <div>
              <strong>Начните с выбора разговора</strong>
              <p>
                Здесь появятся его оценка по критериям, замечания и основания
                для пересмотра.
              </p>
            </div>
          </div>
        ) : !current.ready ? (
          <div className="desk-selected-pending">
            <Clock3 size={25} />
            <div>
              <strong>Диалог ожидает оценки</strong>
              <p>
                Транскрипт доступен. Баллы и замечания появятся после обработки
                сервисом оценивания.
              </p>
            </div>
            <button onClick={() => onOpen(candidate)}>
              Открыть переписку <ArrowUpRight size={14} />
            </button>
          </div>
        ) : (
          <div className="desk-selected-content">
            <div className="desk-selected-score">
              <span className="desk-metric-label">Итоговая оценка</span>
              <strong>
                {format(current.score)}
                <small>/100</small>
              </strong>
              <span className="desk-selected-operator">{candidate.agent}</span>
              <small>
                {applicable} применимых критериев · {naCount} N/A
              </small>
              {current.critical && (
                <span className="desk-critical-label">
                  <ShieldAlert size={13} />
                  Грубая ошибка
                </span>
              )}
              <button onClick={() => onOpen(candidate)}>
                Полный разбор <ArrowRight size={14} />
              </button>
            </div>
            <div className="desk-selected-criteria">
              {snapshot.map((rule) => {
                const result = currentResults.find(
                  (item) => String(item.criterionId) === String(rule.id),
                );
                return (
                  <div
                    className={`desk-preview-criterion ${isIssue(rule, result) ? "has-issue" : ""} ${result?.answer === "N/A" ? "is-na" : ""}`}
                    key={rule.id}
                  >
                    <span>
                      {rule.title}
                      <small>
                        {rule.type === "flag"
                          ? "Отдельный флаг"
                          : `Вес ${rule.weight}`}
                      </small>
                    </span>
                    <strong>{answerLabel(rule, result)}</strong>
                  </div>
                );
              })}
            </div>
            <div className="desk-findings">
              <h3>
                Замечания и апелляция <span>{findings.length}</span>
              </h3>
              {findings.length ? (
                findings.slice(0, 2).map(({ rule, result }) => (
                  <article className="desk-finding" key={rule.id}>
                    <strong>{rule.title}</strong>
                    <p>{result.reason}</p>
                    <button onClick={() => onAppeal?.(candidate, result)}>
                      Оспорить оценку <ArrowUpRight size={12} />
                    </button>
                  </article>
                ))
              ) : (
                <div className="desk-no-findings">
                  <CheckCircle2 size={19} />
                  <strong>Замечаний не выявлено</strong>
                  <p>Все применимые критерии выполнены.</p>
                </div>
              )}
              {findings.length > 2 && (
                <button
                  className="desk-more-findings"
                  onClick={() => onOpen(candidate)}
                >
                  Ещё {findings.length - 2} замечания — открыть разбор{" "}
                  <ArrowRight size={13} />
                </button>
              )}
              <small className="desk-preview-origin">
                Демонстрационная оценка · чек-лист v
                {candidate.checklistVersion || 1}
              </small>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
