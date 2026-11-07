import React, { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowDown,
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  AudioLines,
  Bell,
  BookOpen,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  ChevronsUpDown,
  CircleHelp,
  Clock,
  FileCheck2,
  FileText,
  Filter,
  Globe,
  Headphones,
  LayoutDashboard,
  Leaf,
  MessageCircle,
  MoreHorizontal,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Upload,
  Users,
  X,
  Zap,
  AlertTriangle,
  SlidersHorizontal,
  CheckCircle2,
  PanelLeftClose,
  Menu,
  RefreshCw,
  ExternalLink,
} from "lucide-react";
import {
  initialCriteria,
  conversations as demoConversations,
  scoreEvaluation,
} from "./data";
const icons = {
  overview: LayoutDashboard,
  conversations: MessageCircle,
  criteria: SlidersHorizontal,
  agents: Sparkles,
  appeals: ShieldCheck,
};
const names = {
  overview: "Обзор",
  conversations: "Диалоги",
  criteria: "Критерии оценки",
  agents: "ИИ-команда",
  appeals: "Апелляции",
};
function stored(k, f) {
  try {
    return JSON.parse(localStorage.getItem(k)) ?? f;
  } catch {
    return f;
  }
}
function Avatar({ name, small = false }) {
  return (
    <span className={"avatar " + (small ? "small" : "")}>
      {name
        ?.split(" ")
        .map((s) => s[0])
        .slice(0, 2)
        .join("")}
    </span>
  );
}
function Button({ children, primary = false, ...props }) {
  return (
    <button className={primary ? "button primary" : "button"} {...props}>
      {children}
    </button>
  );
}
function Badge({ status }) {
  return (
    <span className={"badge " + status}>
      <span />
      {status === "done"
        ? "Оценён"
        : status === "review"
          ? "На проверке"
          : "Ожидает оценки"}
    </span>
  );
}
function Modal({ title, onClose, children }) {
  const el = useRef();
  useEffect(() => {
    const prev = document.activeElement;
    el.current?.focus();
    const fn = (e) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab") {
        const a = [
          ...el.current.querySelectorAll(
            'button,input,select,textarea,[tabindex="0"]',
          ),
        ].filter((x) => !x.disabled);
        if (!a.length) return;
        if (e.shiftKey && document.activeElement === a[0]) {
          e.preventDefault();
          a.at(-1).focus();
        } else if (!e.shiftKey && document.activeElement === a.at(-1)) {
          e.preventDefault();
          a[0].focus();
        }
      }
    };
    document.addEventListener("keydown", fn);
    return () => {
      document.removeEventListener("keydown", fn);
      prev?.focus();
    };
  }, []);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        ref={el}
      >
        <div className="modal-head">
          <h2>{title}</h2>
          <button
            className="icon-button"
            onClick={onClose}
            aria-label="Закрыть"
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}
export default function App() {
  const [page, setPage] = useState("overview"),
    [dialogs, setDialogs] = useState(() =>
      stored("sana-dialogs", demoConversations),
    ),
    [criteria, setCriteria] = useState(() =>
      stored("sana-criteria", initialCriteria),
    ),
    [version, setVersion] = useState(() => stored("sana-version", 1)),
    [appeals, setAppeals] = useState(() => stored("sana-appeals", []));
  const [selected, setSelected] = useState(null),
    [search, setSearch] = useState(""),
    [lang, setLang] = useState("Все языки"),
    [channel, setChannel] = useState("Все каналы"),
    [status, setStatus] = useState("Все статусы"),
    [modal, setModal] = useState(null),
    [toast, setToast] = useState(""),
    [mobile, setMobile] = useState(false),
    [period, setPeriod] = useState("Последние 7 дней"),
    [highlight, setHighlight] = useState(null);
  useEffect(() => {
    localStorage.setItem("sana-dialogs", JSON.stringify(dialogs));
  }, [dialogs]);
  useEffect(() => {
    localStorage.setItem("sana-criteria", JSON.stringify(criteria));
    localStorage.setItem("sana-version", JSON.stringify(version));
  }, [criteria, version]);
  useEffect(() => {
    localStorage.setItem("sana-appeals", JSON.stringify(appeals));
  }, [appeals]);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(""), 4500);
    return () => clearTimeout(t);
  }, [toast]);
  function navigate(p) {
    setPage(p);
    setSelected(null);
    setSearch("");
    setMobile(false);
  }
  const filtered = dialogs.filter(
    (d) =>
      (lang === "Все языки" || d.language === lang) &&
      (channel === "Все каналы" || d.channel === channel) &&
      (status === "Все статусы" || d.status === status) &&
      `${d.id} ${d.customer} ${d.agent} ${d.topic}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const evaluated = dialogs.filter(
      (d) => d.status !== "pending" && typeof d.score === "number",
    ),
    average = evaluated.length
      ? Math.round(
          evaluated.reduce((s, d) => s + d.score, 0) / evaluated.length,
        )
      : 0,
    openAppeals = appeals.filter((a) => a.status === "open");
  function exportData() {
    const b = new Blob(
      [
        JSON.stringify(
          {
            demo: true,
            checklistVersion: version,
            criteria,
            conversations: dialogs,
            appeals,
          },
          null,
          2,
        ),
      ],
      { type: "application/json" },
    );
    const a = document.createElement("a");
    a.href = URL.createObjectURL(b);
    a.download = "sana-report.json";
    a.click();
    URL.revokeObjectURL(a.href);
    setToast("Отчёт экспортирован в JSON");
  }
  function evidence(id) {
    setHighlight(id);
    document
      .getElementById("msg-" + id)
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  }
  function saveCriterion(c) {
    setCriteria((old) =>
      old.some((x) => x.id === c.id)
        ? old.map((x) => (x.id === c.id ? c : x))
        : [...old, c],
    );
    setVersion((v) => v + 1);
    setModal(null);
    setToast(
      "Новая версия чек-листа сохранена. Для применения запустите новую оценку через API.",
    );
  }
  return (
    <div className="app-shell">
      <aside className={"sidebar " + (mobile ? "mobile-open" : "")}>
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            navigate("overview");
          }}
        >
          <span className="brand-icon">
            <Leaf size={24} />
          </span>
          sana<span className="brand-dot">.</span>
        </a>
        <div className="workspace">
          <span className="workspace-logo">
            f<span>•</span>
          </span>
          <div>
            <strong>Freedom Broker</strong>
            <small>Рабочее пространство</small>
          </div>
          <ChevronsUpDown size={15} />
        </div>
        <div className="nav-label">ПЛАТФОРМА</div>
        <nav>
          {Object.entries(names).map(([key, title]) => {
            const Icon = icons[key];
            return (
              <button
                key={key}
                onClick={() => navigate(key)}
                className={"nav-item " + (page === key ? "active" : "")}
              >
                <Icon size={19} />
                <span>{title}</span>
                {key === "conversations" && <em>{dialogs.length}</em>}
                {key === "appeals" && openAppeals.length > 0 && (
                  <em>{openAppeals.length}</em>
                )}
              </button>
            );
          })}
        </nav>
        <div className="sidebar-bottom">
          <div className="insight-card">
            <span className="insight-icon">
              <Sparkles size={18} />
            </span>
            <strong>Замечайте больше.</strong>
            <p>Каждый разговор — источник новых возможностей.</p>
            <button onClick={() => navigate("agents")}>
              Познакомиться с ИИ <ArrowUpRight size={15} />
            </button>
          </div>
          <button
            className="nav-item"
            onClick={() => setModal({ type: "help" })}
          >
            <CircleHelp size={18} />
            <span>Помощь и поддержка</span>
            <ArrowUpRight size={14} />
          </button>
          <div className="profile">
            <Avatar name="Алина Садыкова" />
            <div>
              <strong>Алина Садыкова</strong>
              <small>Администратор</small>
            </div>
            <button
              className="icon-button"
              aria-label="Информация о профиле"
              onClick={() => setModal({ type: "profile" })}
            >
              <MoreHorizontal size={19} />
            </button>
          </div>
        </div>
      </aside>
      {mobile && (
        <div className="mobile-scrim" onClick={() => setMobile(false)} />
      )}
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            <button
              className="icon-button mobile-menu"
              aria-label="Открыть меню"
              onClick={() => setMobile(true)}
            >
              <Menu size={20} />
            </button>
            <span>Рабочее пространство</span>
            <ChevronRight size={14} />
            <strong>{names[page]}</strong>
          </div>
          <div className="topbar-actions">
            <span className="demo-chip">
              <span />
              Демо-данные
            </span>
            <button
              className="icon-button notification"
              aria-label="Уведомления"
              onClick={() => setModal({ type: "notifications" })}
            >
              <Bell size={19} />
              <i />
            </button>
            <div className="header-divider" />
            <Avatar name="Алина Садыкова" small />
          </div>
        </header>
        <main>
          {selected ? (
            <>
              <button className="back-link" onClick={() => setSelected(null)}>
                <ArrowLeft size={16} /> К списку диалогов
              </button>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">
                    КАРТОЧКА ДИАЛОГА · {selected.id}
                  </div>
                  <h1>{selected.topic}</h1>
                  <p>
                    {selected.customer} <span className="dot-sep">•</span>{" "}
                    {selected.language} <span className="dot-sep">•</span>{" "}
                    {selected.duration}
                  </p>
                </div>
                <Badge status={selected.status} />
              </div>
              <div className="detail-grid">
                <section className="panel transcript">
                  <div className="panel-heading">
                    <h2>
                      <MessageCircle size={18} /> Транскрипт
                    </h2>
                    <span className="muted">
                      {selected.messages.length} реплик
                    </span>
                  </div>
                  {selected.channel === "call" && (
                    <div className="audio-note">
                      <AudioLines size={20} />
                      <div>
                        <strong>Запись разговора</strong>
                        <small>
                          {selected.audio_url
                            ? "Открыть оригинальную запись"
                            : "В демо доступен только транскрипт"}
                        </small>
                      </div>
                      {selected.audio_url && (
                        <a
                          href={selected.audio_url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          <ExternalLink size={18} />
                        </a>
                      )}
                    </div>
                  )}
                  <div className="messages">
                    {selected.messages.map((m) => (
                      <div
                        id={"msg-" + m.id}
                        key={m.id}
                        className={
                          "message " +
                          m.role +
                          (highlight === m.id ? " highlighted" : "")
                        }
                      >
                        <div className="message-meta">
                          <span>
                            {m.role === "operator"
                              ? selected.agent
                              : m.role === "system"
                                ? "Система"
                                : m.role === "bot"
                                  ? "Бот"
                                  : selected.customer}
                          </span>
                          <time>{m.time}</time>
                        </div>
                        <p>{m.text}</p>
                        <small>#{m.id}</small>
                      </div>
                    ))}
                  </div>
                </section>
                <section className="panel evaluation">
                  <div className="panel-heading">
                    <h2>Оценка качества</h2>
                    <span className="version-pill">
                      v{selected.checklistVersion || 1}
                    </span>
                  </div>
                  <div className="evaluation-total">
                    <div>
                      <span className="muted">Итоговый балл</span>
                      <strong>
                        {selected.score ?? "—"}
                        <small>/100</small>
                      </strong>
                    </div>
                    <div className="score-orbit">
                      <ShieldCheck size={30} />
                    </div>
                  </div>
                  <div className="original-note">
                    {selected.originalScore !== undefined
                      ? `Исходная оценка: ${selected.originalScore} · результат после пересмотра`
                      : "Демонстрационная оценка · не результат запуска модели"}
                  </div>
                  <div className="criteria-results">
                    {selected.critical && (
                      <div className="critical-notice">
                        <AlertTriangle size={16} />
                        Выявлена грубая ошибка. Флаг учитывается отдельно от
                        балла.
                      </div>
                    )}
                    {(selected.results || []).map((r) => {
                      const c = (
                        selected.criteriaSnapshot || initialCriteria
                      ).find((c) => c.id === r.criterionId);
                      return (
                        <div className="criterion-result" key={r.criterionId}>
                          <div className="criterion-title">
                            <span>
                              {c?.title || "Критерий " + r.criterionId}
                            </span>
                            <b
                              className={
                                r.answer === "Нет" && c?.type !== "flag"
                                  ? "negative"
                                  : r.answer === "N/A"
                                    ? "na"
                                    : "positive"
                              }
                            >
                              {r.answer}
                              {typeof r.answer === "number"
                                ? "/" + Math.max(...(c?.scale || [20]))
                                : ""}
                            </b>
                          </div>
                          <p>{r.reason}</p>
                          {selected.originalResults &&
                            selected.originalResults.find(
                              (o) => o.criterionId === r.criterionId,
                            )?.answer !== r.answer && (
                              <p className="original-answer">
                                До пересмотра:{" "}
                                {
                                  selected.originalResults.find(
                                    (o) => o.criterionId === r.criterionId,
                                  )?.answer
                                }
                              </p>
                            )}
                          <div className="criterion-actions">
                            <button onClick={() => evidence(r.evidenceId)}>
                              <FileText size={13} /> Реплика #{r.evidenceId}
                            </button>
                            <button
                              onClick={() =>
                                setModal({
                                  type: "appeal",
                                  dialog: selected,
                                  result: r,
                                })
                              }
                            >
                              Оспорить <ArrowUpRight size={13} />
                            </button>
                          </div>
                        </div>
                      );
                    })}
                    {!selected.results?.length && (
                      <div className="empty-state">
                        <Clock />
                        <h3>Ожидает оценки</h3>
                        <p>
                          Диалог импортирован. Для анализа подключите сервис
                          оценивания.
                        </p>
                      </div>
                    )}
                  </div>
                </section>
              </div>
            </>
          ) : (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">
                    CONVERSATION INTELLIGENCE <span>✦</span>
                  </div>
                  <h1>
                    {page === "overview" ? "Обзор качества" : names[page]}
                  </h1>
                  <p>
                    {page === "overview"
                      ? "Хорошие разговоры начинаются с понимания. Вот ваша общая картина."
                      : page === "conversations"
                        ? "Все разговоры, важные детали и возможности для роста."
                        : page === "criteria"
                          ? "Ваш стандарт качества. Гибкие правила для каждого разговора."
                          : page === "agents"
                            ? "Специализированные роли, которые видят разговор с разных сторон."
                            : "Прозрачный пересмотр. Каждое решение имеет значение."}
                  </p>
                </div>
                <div className="heading-actions">
                  {page === "criteria" ? (
                    <Button
                      primary
                      onClick={() =>
                        setModal({
                          type: "criterion",
                          criterion: {
                            id: crypto.randomUUID(),
                            title: "",
                            description: "",
                            weight: 10,
                            type: "binary",
                            scale: [],
                            naAllowed: false,
                            naCondition: "",
                          },
                        })
                      }
                    >
                      <Plus size={17} />
                      Добавить критерий
                    </Button>
                  ) : (
                    <>
                      <Button onClick={exportData}>
                        <ArrowDownToLine size={16} />
                        Экспорт
                      </Button>
                      <Button
                        primary
                        onClick={() => setModal({ type: "import" })}
                      >
                        <Plus size={18} />
                        Загрузить диалоги
                      </Button>
                    </>
                  )}
                </div>
              </div>
              {page === "overview" && (
                <>
                  <div className="toolbar overview-toolbar">
                    <div className="segmented">
                      <button className="selected">Общая аналитика</button>
                      <button onClick={() => navigate("agents")}>
                        Работа ИИ-команды <Sparkles size={13} />
                      </button>
                    </div>
                    <select
                      aria-label="Период аналитики"
                      value={period}
                      onChange={(e) => setPeriod(e.target.value)}
                    >
                      <option>Последние 7 дней</option>
                      <option>Последние 30 дней</option>
                    </select>
                  </div>
                  <div className="stats-grid">
                    <Stat
                      title="Проанализировано диалогов"
                      value={evaluated.length.toString().padStart(2, "0")}
                      icon={MessageCircle}
                      note={`из ${dialogs.length} диалогов в наборе`}
                    />
                    <Stat
                      title="Средняя оценка качества"
                      value={average}
                      suffix="/100"
                      icon={Activity}
                      note="по завершённым оценкам"
                      green
                    />
                    <Stat
                      title="Требуют внимания"
                      value={dialogs
                        .filter((d) => d.status === "review")
                        .length.toString()
                        .padStart(2, "0")}
                      icon={ShieldCheck}
                      note="диалогов на проверке"
                      orange
                    />
                    <Stat
                      title="Активных апелляций"
                      value={openAppeals.length.toString().padStart(2, "0")}
                      icon={FileCheck2}
                      note="ожидают вашего решения"
                    />
                  </div>
                  <div className="charts-grid">
                    <section className="panel trend-panel">
                      <div className="panel-heading">
                        <div>
                          <h2>Качество в динамике</h2>
                          <p>Каждый день — чуть лучше</p>
                        </div>
                        <div className="chart-legend">
                          <span />
                          Средняя оценка{" "}
                          <button
                            className="icon-button"
                            aria-label="Объяснение графика"
                            onClick={() =>
                              setToast(
                                "График иллюстрирует демо-динамику. Реальные временные ряды подключаются через API.",
                              )
                            }
                          >
                            <MoreHorizontal size={18} />
                          </button>
                        </div>
                      </div>
                      <Trend period={period} />
                      <div className="chart-foot">
                        <span>
                          <span className="tiny-star">✦</span> Демо-динамика
                          качества разговоров
                        </span>
                        <span>Шкала 0–100</span>
                      </div>
                    </section>
                    <section className="panel criteria-summary">
                      <div className="panel-heading">
                        <h2>В разрезе критериев</h2>
                        <button
                          className="icon-button"
                          aria-label="Все критерии"
                          onClick={() => navigate("criteria")}
                        >
                          <ArrowUpRight size={19} />
                        </button>
                      </div>
                      <p className="panel-subtitle">
                        Где всё хорошо, а где есть потенциал
                      </p>
                      {[
                        { label: "Установление контакта", v: 96 },
                        { label: "Выявление потребности", v: 84 },
                        { label: "Корректность консультации", v: 78 },
                        { label: "Эмпатия", v: 92 },
                        { label: "Завершение диалога", v: 72 },
                      ].map((c, i) => (
                        <div className="progress-item" key={c.label}>
                          <div>
                            <span>{c.label}</span>
                            <strong>
                              {c.v}
                              <small>/100</small>
                            </strong>
                          </div>
                          <div className="progress-track">
                            <span
                              style={{
                                width: c.v + "%",
                                background:
                                  i === 2 || i === 4 ? "#d5a77b" : undefined,
                              }}
                            />
                          </div>
                        </div>
                      ))}
                      <button
                        className="text-link"
                        onClick={() => navigate("criteria")}
                      >
                        Все {criteria.length} критериев <ArrowRight size={14} />
                      </button>
                      <small className="demo-caption">
                        Иллюстративные показатели
                      </small>
                    </section>
                  </div>
                  <div className="agent-banner">
                    <span className="agent-banner-icon">
                      <Sparkles size={22} />
                    </span>
                    <div>
                      <strong>Один разговор. Несколько точек зрения.</strong>
                      <p>
                        ИИ-агенты находят факты, проверяют критерии и объясняют
                        каждый вывод.
                      </p>
                    </div>
                    <div className="agent-mini-icons">
                      <span>
                        <Search size={15} />
                      </span>
                      <span>
                        <Users size={15} />
                      </span>
                      <span>
                        <ShieldCheck size={15} />
                      </span>
                    </div>
                    <button onClick={() => navigate("agents")}>
                      Ваша ИИ-команда <ArrowUpRight size={16} />
                    </button>
                  </div>
                </>
              )}
              {(page === "overview" || page === "conversations") && (
                <section className="panel table-panel">
                  <div className="panel-heading">
                    <div className="title-with-count">
                      <h2>
                        {page === "overview"
                          ? "Последние диалоги"
                          : "Все диалоги"}
                      </h2>
                      <span className="count-pill">{dialogs.length}</span>
                    </div>
                    {page === "overview" && (
                      <button
                        className="text-link"
                        onClick={() => navigate("conversations")}
                      >
                        Все диалоги <ArrowRight size={14} />
                      </button>
                    )}
                  </div>
                  <div className="table-toolbar">
                    <label className="search-field">
                      <Search size={16} />
                      <input
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Поиск по диалогам, клиентам..."
                        aria-label="Поиск диалогов"
                      />
                    </label>
                    <div className="filters">
                      <select
                        aria-label="Язык"
                        value={lang}
                        onChange={(e) => setLang(e.target.value)}
                      >
                        <option>Все языки</option>
                        <option>RU</option>
                        <option>KZ</option>
                        <option>EN</option>
                      </select>
                      <select
                        aria-label="Канал"
                        value={channel}
                        onChange={(e) => setChannel(e.target.value)}
                      >
                        <option>Все каналы</option>
                        <option value="chat">Чаты</option>
                        <option value="call">Звонки</option>
                      </select>
                      <select
                        aria-label="Статус"
                        value={status}
                        onChange={(e) => setStatus(e.target.value)}
                      >
                        <option>Все статусы</option>
                        <option value="done">Оценён</option>
                        <option value="review">На проверке</option>
                        <option value="pending">Ожидает оценки</option>
                      </select>
                    </div>
                  </div>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Диалог</th>
                          <th>Оператор</th>
                          <th>Канал</th>
                          <th>
                            Оценка <ArrowDown size={12} />
                          </th>
                          <th>Статус</th>
                          <th>Время</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {filtered
                          .slice(0, page === "overview" ? 5 : 100)
                          .map((d) => (
                            <tr key={d.id} onClick={() => setSelected(d)}>
                              <td>
                                <button
                                  className="dialog-button"
                                  onClick={() => setSelected(d)}
                                >
                                  <span
                                    className={
                                      "conversation-icon " +
                                      (d.channel === "call" ? "call" : "")
                                    }
                                  >
                                    {d.channel === "call" ? (
                                      <Headphones size={17} />
                                    ) : (
                                      <MessageCircle size={17} />
                                    )}
                                  </span>
                                  <span>
                                    <strong>{d.topic}</strong>
                                    <small>
                                      {d.id} <span>·</span> {d.customer}
                                    </small>
                                  </span>
                                </button>
                              </td>
                              <td>
                                <div className="operator">
                                  <Avatar name={d.agent} small />
                                  <span>{d.agent}</span>
                                </div>
                              </td>
                              <td>
                                <span className="channel-label">
                                  {d.channel === "call" ? "Звонок" : "Чат"}
                                </span>
                                <span className="language">{d.language}</span>
                              </td>
                              <td>
                                {d.status === "pending" ? (
                                  <span className="muted">—</span>
                                ) : (
                                  <span
                                    className={
                                      "score " +
                                      (d.score >= 85
                                        ? "high"
                                        : d.score >= 70
                                          ? "mid"
                                          : "low")
                                    }
                                  >
                                    {d.score}
                                    <small>/100</small>
                                  </span>
                                )}
                              </td>
                              <td>
                                <Badge status={d.status} />
                              </td>
                              <td className="date-cell">{d.date}</td>
                              <td>
                                <ChevronRight size={16} />
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                  {filtered.length === 0 && (
                    <div className="empty-state">
                      <Search />
                      <h3>Ничего не найдено</h3>
                      <p>Попробуйте изменить поиск или фильтры.</p>
                      <button
                        className="text-link"
                        onClick={() => {
                          setSearch("");
                          setLang("Все языки");
                          setChannel("Все каналы");
                          setStatus("Все статусы");
                        }}
                      >
                        Сбросить фильтры
                      </button>
                    </div>
                  )}
                  <div className="table-footer">
                    <span>
                      Показано{" "}
                      {Math.min(filtered.length, page === "overview" ? 5 : 100)}{" "}
                      из {filtered.length} диалогов
                    </span>
                    <span className="live-label">
                      <span />
                      Демонстрационный набор
                    </span>
                  </div>
                </section>
              )}
              {page === "criteria" && (
                <>
                  <div className="notice">
                    <BookOpen size={19} />
                    <div>
                      <strong>
                        Чек-лист Freedom Broker{" "}
                        <span className="version-pill">v{version}</span>
                      </strong>
                      <p>
                        Изменения создают новую версию. Существующие оценки
                        сохраняют исходные правила.
                      </p>
                    </div>
                  </div>
                  <div className="criteria-grid">
                    {criteria.map((c, i) => (
                      <article className="panel criterion-card" key={c.id}>
                        <div className="criterion-card-top">
                          <span className="criterion-number">
                            {String(i + 1).padStart(2, "0")}
                          </span>
                          <span className="version-pill">
                            {c.type === "flag"
                              ? "Отдельный флаг"
                              : c.weight + " баллов"}
                          </span>
                        </div>
                        <h2>{c.title}</h2>
                        <p>{c.description}</p>
                        <div className="criterion-card-bottom">
                          <span>
                            {c.type === "scale"
                              ? c.scale.join(" / ")
                              : "Да / Нет"}
                            {c.naAllowed ? " / N/A" : ""}
                          </span>
                          <button
                            onClick={() =>
                              setModal({ type: "criterion", criterion: c })
                            }
                          >
                            Настроить <SlidersHorizontal size={14} />
                          </button>
                        </div>
                      </article>
                    ))}
                  </div>
                </>
              )}
              {page === "agents" && (
                <>
                  <div className="notice">
                    <Sparkles size={20} />
                    <div>
                      <strong>Специализация вместо случайных мнений</strong>
                      <p>
                        Шесть логических ролей. Баллы рассчитываются программно
                        по версии чек-листа.
                      </p>
                    </div>
                    <span className="demo-chip">Демо</span>
                  </div>
                  <div className="agents-grid">
                    {[
                      {
                        icon: Search,
                        name: "Extractor",
                        role: "Находит важное",
                        text: "Извлекает факты, вопросы клиента и действия оператора. Сохраняет связь с исходными репликами.",
                        color: "mint",
                      },
                      {
                        icon: Globe,
                        name: "Classifier",
                        role: "Понимает контекст",
                        text: "Определяет темы и категории обращений на русском, казахском и английском.",
                        color: "blue",
                      },
                      {
                        icon: Users,
                        name: "Customer Analyst",
                        role: "Слышит клиента",
                        text: "Анализирует потребности, неудобства и реакцию оператора на недовольство клиента.",
                        color: "peach",
                      },
                      {
                        icon: FileCheck2,
                        name: "Process Analyst",
                        role: "Проверяет по правилам",
                        text: "Применяет актуальную версию критериев. Новый критерий передаётся универсальному оценщику.",
                        color: "mint",
                      },
                      {
                        icon: ShieldCheck,
                        name: "Critic",
                        role: "Проверяет доказательства",
                        text: "Ищет противоречия, проверяет ссылки на реплики и обоснованность N/A.",
                        color: "purple",
                      },
                      {
                        icon: Zap,
                        name: "Business Strategist",
                        role: "Превращает выводы в действия",
                        text: "Формирует рекомендации по завершённым оценкам. Не влияет на итоговый балл.",
                        color: "peach",
                      },
                    ].map((a, i) => (
                      <article className="panel agent-card" key={a.name}>
                        <div className={"agent-card-icon " + a.color}>
                          <a.icon size={24} />
                        </div>
                        <span className="agent-index">0{i + 1}</span>
                        <h2>{a.name}</h2>
                        <strong>{a.role}</strong>
                        <p>{a.text}</p>
                        <div className="agent-card-footer">
                          <span className="muted">Подключение через API</span>
                          <span className="status-dot" />
                        </div>
                      </article>
                    ))}
                  </div>
                  <div className="panel architecture-note">
                    <Activity size={22} />
                    <div>
                      <h2>Прозрачный путь к оценке</h2>
                      <p>
                        Факты → специализированные оценщики → проверка
                        доказательств → расчёт баллов → дашборд
                      </p>
                      <small>
                        В этой версии интерфейса модели не запускаются. Карточки
                        описывают запланированные роли.
                      </small>
                    </div>
                  </div>
                </>
              )}
              {page === "appeals" && (
                <section className="panel">
                  <div className="panel-heading">
                    <h2>Обращения на пересмотр</h2>
                    <span className="count-pill">{appeals.length}</span>
                  </div>
                  {!appeals.length ? (
                    <div className="empty-state large">
                      <div className="empty-icon">
                        <ShieldCheck size={30} />
                      </div>
                      <h3>Каждое мнение важно</h3>
                      <p>
                        Чтобы подать апелляцию, откройте диалог
                        <br />и нажмите «Оспорить» у нужного критерия.
                      </p>
                      <Button onClick={() => navigate("conversations")}>
                        Перейти к диалогам <ArrowRight size={16} />
                      </Button>
                    </div>
                  ) : (
                    appeals.map((a) => (
                      <div className="appeal-row" key={a.id}>
                        <span className="conversation-icon">
                          <FileCheck2 size={20} />
                        </span>
                        <div>
                          <strong>{a.title}</strong>
                          <small>
                            {a.dialogId} · {a.date}
                          </small>
                          <p>{a.comment}</p>
                          {a.decision && (
                            <p className="decision-text">
                              Решение: {a.newAnswer} · {a.decision}
                            </p>
                          )}
                        </div>
                        <span
                          className={
                            "badge " + (a.status === "open" ? "review" : "done")
                          }
                        >
                          {a.status === "open"
                            ? "На рассмотрении"
                            : "Рассмотрена"}
                        </span>
                        {a.status === "open" && (
                          <Button
                            onClick={() =>
                              setModal({ type: "decision", appeal: a })
                            }
                          >
                            Рассмотреть <ArrowUpRight size={15} />
                          </Button>
                        )}
                      </div>
                    ))
                  )}
                </section>
              )}
              <footer className="page-footer">
                <span>
                  <Leaf size={13} /> sana — больше смысла в каждом разговоре
                </span>
                <span>
                  RU · KZ · EN <span className="dot-sep">•</span> CQA workspace
                </span>
              </footer>
            </>
          )}
        </main>
      </div>
      {toast && (
        <div role="status" className="toast">
          <CheckCircle2 size={18} />
          {toast}
          <button onClick={() => setToast("")} aria-label="Скрыть уведомление">
            <X size={16} />
          </button>
        </div>
      )}
      {modal && (
        <Modal
          title={
            modal.type === "criterion"
              ? "Настройка критерия"
              : modal.type === "import"
                ? "Загрузить диалоги"
                : modal.type === "appeal"
                  ? "Оспорить оценку"
                  : modal.type === "decision"
                    ? "Решение проверяющего"
                    : modal.type === "help"
                      ? "Как работает Sana"
                      : modal.type === "profile"
                        ? "Ваше рабочее пространство"
                        : "Уведомления"
          }
          onClose={() => setModal(null)}
        >
          {modal.type === "criterion" ? (
            <CriterionForm criterion={modal.criterion} onSave={saveCriterion} />
          ) : modal.type === "import" ? (
            <ImportForm
              existing={dialogs}
              onImport={(items) => {
                setDialogs((old) => [...items, ...old]);
                setModal(null);
                navigate("conversations");
                setToast(
                  `Загружено диалогов: ${items.length}. Для оценивания требуется серверный API.`,
                );
              }}
            />
          ) : modal.type === "appeal" ? (
            <AppealForm
              onSubmit={(comment) => {
                setAppeals((old) => [
                  {
                    id: crypto.randomUUID(),
                    dialogId: modal.dialog.id,
                    criterionId: modal.result.criterionId,
                    title:
                      (modal.dialog.criteriaSnapshot || initialCriteria).find(
                        (c) => c.id === modal.result.criterionId,
                      )?.title || "Критерий",
                    criterion: (
                      modal.dialog.criteriaSnapshot || initialCriteria
                    ).find((c) => c.id === modal.result.criterionId),
                    originalAnswer: modal.result.answer,
                    comment,
                    status: "open",
                    date: new Date().toLocaleDateString("ru-RU"),
                  },
                  ...old,
                ]);
                setModal(null);
                setToast(
                  "Апелляция сохранена. Откройте раздел «Апелляции», чтобы рассмотреть её.",
                );
              }}
            />
          ) : modal.type === "decision" ? (
            <DecisionForm
              appeal={modal.appeal}
              onOpenDialog={() => {
                const d = dialogs.find((d) => d.id === modal.appeal.dialogId);
                setSelected(d);
                setModal(null);
                setHighlight(null);
              }}
              onSave={(answer, reason) => {
                const a = modal.appeal;
                setDialogs((old) =>
                  old.map((d) => {
                    if (d.id !== a.dialogId) return d;
                    const results = d.results.map((r) =>
                      r.criterionId === a.criterionId
                        ? { ...r, answer, reason }
                        : r,
                    );
                    const calculated = scoreEvaluation(
                      d.criteriaSnapshot || initialCriteria,
                      results,
                    );
                    return {
                      ...d,
                      results,
                      originalResults: d.originalResults || d.results,
                      originalScore: d.originalScore ?? d.score,
                      score: calculated.score,
                      critical: calculated.critical,
                      status: "done",
                    };
                  }),
                );
                setAppeals((old) =>
                  old.map((x) =>
                    x.id === a.id
                      ? {
                          ...x,
                          status: "resolved",
                          newAnswer: answer,
                          decision: reason,
                        }
                      : x,
                  ),
                );
                setModal(null);
                setToast("Решение сохранено. Итоговый балл пересчитан.");
              }}
            />
          ) : modal.type === "help" ? (
            <div className="modal-content">
              <p>1. Откройте диалог и изучите оценку рядом с транскриптом.</p>
              <p>
                2. Нажмите на ссылку под критерием, чтобы найти
                реплику-доказательство.
              </p>
              <p>
                3. Настройте чек-лист или подайте апелляцию на спорный ответ.
              </p>
              <div className="notice">
                Это интерактивный прототип на синтетических данных. Все
                изменения сохраняются в вашем браузере. Реальные оценки требуют
                подключения серверного API.
              </div>
            </div>
          ) : modal.type === "profile" ? (
            <div className="modal-content">
              <Avatar name="Алина Садыкова" />
              <h3>Алина Садыкова</h3>
              <p>Freedom Broker · Администратор</p>
              <p>
                Демонстрационный профиль. Авторизация для прототипа не
                требуется.
              </p>
            </div>
          ) : (
            <div className="modal-content">
              <div className="notice">
                <CheckCheck size={20} />
                <div>
                  <strong>Вы в курсе всего</strong>
                  <p>
                    Новых системных уведомлений нет.{" "}
                    {openAppeals.length
                      ? `Открытых апелляций: ${openAppeals.length}.`
                      : "Новые апелляции появятся в соответствующем разделе."}
                  </p>
                </div>
              </div>
            </div>
          )}
        </Modal>
      )}
    </div>
  );
}
function Stat({ title, value, suffix, icon: Icon, note, green, orange }) {
  return (
    <article className={"panel stat " + (green ? "featured" : "")}>
      <div className="stat-top">
        <span>{title}</span>
        <span className={"stat-icon " + (orange ? "orange" : "")}>
          <Icon size={17} />
        </span>
      </div>
      <div className="stat-value">
        {value}
        <span>{suffix}</span>
        {green && <span className="mini-spark">▁▂▂▄▃▅▆▇</span>}
      </div>
      <div className="stat-note">
        <span className={orange ? "orange-dot" : "green-dot"} />
        {note}
      </div>
    </article>
  );
}
function Trend({ period }) {
  const month = period.includes("30");
  return (
    <div className="trend-chart">
      <div className="y-labels">
        <span>100</span>
        <span>80</span>
        <span>60</span>
        <span>40</span>
      </div>
      <div className="plot">
        <svg
          viewBox="0 0 700 190"
          preserveAspectRatio="none"
          role="img"
          aria-label="Демонстрационный график динамики качества"
        >
          <defs>
            <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#81c6aa" stopOpacity=".27" />
              <stop offset="100%" stopColor="#81c6aa" stopOpacity=".015" />
            </linearGradient>
          </defs>
          {[20, 70, 120, 170].map((y) => (
            <line
              key={y}
              x1="0"
              y1={y}
              x2="700"
              y2={y}
              stroke="#edf0ed"
              strokeDasharray="4 5"
            />
          ))}
          <path
            d={
              month
                ? "M0 135 C40 120 70 155 110 120 S180 70 230 85 S300 125 350 75 S440 105 470 55 S560 80 590 45 S650 70 700 30 L700 190 L0 190Z"
                : "M0 135 C45 135 65 75 115 91 S185 135 230 90 S300 55 350 72 S420 83 470 48 S550 78 590 50 S650 38 700 20 L700 190 L0 190Z"
            }
            fill="url(#area)"
          />
          <path
            d={
              month
                ? "M0 135 C40 120 70 155 110 120 S180 70 230 85 S300 125 350 75 S440 105 470 55 S560 80 590 45 S650 70 700 30"
                : "M0 135 C45 135 65 75 115 91 S185 135 230 90 S300 55 350 72 S420 83 470 48 S550 78 590 50 S650 38 700 20"
            }
            fill="none"
            stroke="#3c9372"
            strokeWidth="2.7"
          />
          <line
            x1="470"
            y1="15"
            x2="470"
            y2="185"
            stroke="#b4d6c4"
            strokeDasharray="4 4"
          />
          <circle
            cx="470"
            cy={month ? 55 : 48}
            r="5"
            fill="#fff"
            stroke="#3c9372"
            strokeWidth="3"
          />
        </svg>
        <div className="chart-tooltip">
          <small>{month ? "20 октября" : "5 ноября"}</small>
          <strong>
            {month ? "86" : "89"} <span>баллов</span>
          </strong>
        </div>
        <div className="x-labels">
          {(month
            ? [
                "9 окт",
                "14 окт",
                "19 окт",
                "24 окт",
                "29 окт",
                "3 ноя",
                "7 ноя",
              ]
            : ["1 ноя", "2 ноя", "3 ноя", "4 ноя", "5 ноя", "6 ноя", "7 ноя"]
          ).map((d) => (
            <span key={d}>{d}</span>
          ))}
        </div>
      </div>
    </div>
  );
}
function CriterionForm({ criterion, onSave }) {
  const [c, setC] = useState({ ...criterion }),
    [error, setError] = useState("");
  function submit(e) {
    e.preventDefault();
    const scale =
      c.type === "scale"
        ? String(c.scale)
            .split(",")
            .map((x) => Number(x.trim()))
        : [];
    if (!c.title.trim() || !c.description.trim())
      return setError("Заполните название и правило оценки.");
    if (
      c.type === "scale" &&
      (scale.length < 2 ||
        scale.some((x) => !Number.isFinite(x) || x < 0) ||
        Math.max(...scale) <= 0 ||
        new Set(scale).size !== scale.length)
    )
      return setError(
        "Укажите минимум две разные неотрицательные ступени, например 0, 5, 10, 15, 20.",
      );
    if (c.naAllowed && !c.naCondition.trim())
      return setError("Опишите условие неприменимости N/A.");
    onSave({
      ...c,
      weight: c.type === "flag" ? 0 : Number(c.weight),
      scale: scale.sort((a, b) => a - b),
    });
  }
  return (
    <form className="form" onSubmit={submit}>
      <label>
        Название
        <input
          required
          value={c.title}
          onChange={(e) => setC({ ...c, title: e.target.value })}
        />
      </label>
      <label>
        Правило оценки
        <textarea
          required
          rows={4}
          value={c.description}
          onChange={(e) => setC({ ...c, description: e.target.value })}
        />
      </label>
      <div className="form-row">
        <label>
          Тип ответа
          <select
            value={c.type}
            onChange={(e) =>
              setC({
                ...c,
                type: e.target.value,
                naAllowed: e.target.value === "flag" ? false : c.naAllowed,
              })
            }
          >
            <option value="binary">Да / Нет</option>
            <option value="scale">Числовая шкала</option>
            <option value="flag">Отдельный флаг</option>
          </select>
        </label>
        <label>
          Вес
          <input
            type="number"
            min="0"
            max="1000"
            required
            disabled={c.type === "flag"}
            value={c.type === "flag" ? 0 : c.weight}
            onChange={(e) => setC({ ...c, weight: e.target.value })}
          />
        </label>
      </div>
      {c.type === "scale" && (
        <label>
          Ступени через запятую
          <input
            required
            value={String(c.scale)}
            onChange={(e) => setC({ ...c, scale: e.target.value })}
          />
        </label>
      )}
      <label className="checkbox-label">
        <input
          type="checkbox"
          checked={c.naAllowed}
          disabled={c.type === "flag"}
          onChange={(e) => setC({ ...c, naAllowed: e.target.checked })}
        />
        Разрешить N/A
      </label>
      {c.naAllowed && (
        <label>
          Когда критерий неприменим
          <textarea
            required
            value={c.naCondition}
            onChange={(e) => setC({ ...c, naCondition: e.target.value })}
          />
        </label>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <div className="form-footer">
        <span>Сохранение создаст новую версию</span>
        <Button primary type="submit">
          <Check size={16} />
          Сохранить
        </Button>
      </div>
    </form>
  );
}
function AppealForm({ onSubmit }) {
  const [comment, setComment] = useState("");
  return (
    <form
      className="form"
      onSubmit={(e) => {
        e.preventDefault();
        if (comment.trim()) onSubmit(comment.trim());
      }}
    >
      <p className="muted">
        Расскажите, с чем вы не согласны. Проверяющий увидит исходную оценку и
        ваше объяснение.
      </p>
      <label>
        Причина апелляции
        <textarea
          rows={5}
          required
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Укажите, какая реплика подтверждает вашу позицию..."
        />
      </label>
      <Button primary type="submit">
        Отправить на пересмотр <ArrowRight size={16} />
      </Button>
    </form>
  );
}
function DecisionForm({ appeal, onSave, onOpenDialog }) {
  const c =
      appeal.criterion ||
      initialCriteria.find((c) => c.id === appeal.criterionId),
    values = c?.type === "scale" ? c.scale : ["Да", "Нет"];
  const [answer, setAnswer] = useState(appeal.originalAnswer),
    [reason, setReason] = useState("");
  return (
    <form
      className="form"
      onSubmit={(e) => {
        e.preventDefault();
        if (reason.trim()) onSave(answer, reason.trim());
      }}
    >
      <div className="notice">
        <div>
          <strong>
            {appeal.title} · исходный ответ: {appeal.originalAnswer}
          </strong>
          <p>{appeal.comment}</p>
          <button type="button" className="text-link" onClick={onOpenDialog}>
            Посмотреть транскрипт и доказательства <ArrowUpRight size={14} />
          </button>
        </div>
      </div>
      <label>
        Ответ после проверки
        <select
          value={answer}
          onChange={(e) =>
            setAnswer(
              c?.type === "scale" && e.target.value !== "N/A"
                ? Number(e.target.value)
                : e.target.value,
            )
          }
        >
          {[...values, ...(c?.naAllowed ? ["N/A"] : [])].map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
      </label>
      <label>
        Обоснование решения
        <textarea
          required
          rows={4}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      <Button primary type="submit">
        <CheckCheck size={16} />
        Сохранить и пересчитать
      </Button>
    </form>
  );
}
function ImportForm({ existing, onImport }) {
  const [raw, setRaw] = useState(""),
    [error, setError] = useState("");
  function parse() {
    try {
      const data = JSON.parse(raw),
        records = Array.isArray(data)
          ? data
          : data?.data?.records || data?.records;
      if (!Array.isArray(records) || !records.length)
        throw Error(
          "Нужен непустой массив records или ответ API организаторов.",
        );
      const ids = new Set(existing.map((d) => d.id));
      const list = records.map((r, i) => {
        if (!["agent chat", "voice call"].includes(r.channel))
          throw Error("Канал должен быть agent chat или voice call.");
        if (
          !r.conversation_id ||
          !Array.isArray(r.transcript) ||
          !r.transcript.length
        )
          throw Error(
            `Запись ${i + 1}: нужны conversation_id и непустой transcript.`,
          );
        if (ids.has(r.conversation_id))
          throw Error(
            `Диалог ${r.conversation_id} уже существует или повторяется.`,
          );
        ids.add(r.conversation_id);
        if (!["RU", "KZ", "EN"].includes(r.language))
          throw Error("Допустимые языки: RU, KZ, EN.");
        const messages = r.transcript.map((m, j) => {
          if (
            !["client", "operator", "bot", "system"].includes(m.speaker) ||
            typeof m.text !== "string" ||
            typeof m.timestamp !== "string"
          )
            throw Error(`Некорректная реплика ${j + 1}.`);
          return {
            id: "m" + (j + 1),
            role: m.speaker,
            text: m.text,
            time: m.timestamp,
          };
        });
        let audio = null;
        if (r.audio_url) {
          const u = new URL(r.audio_url);
          if (u.protocol !== "https:")
            throw Error("Для аудио нужна HTTPS-ссылка.");
          audio = u.href;
        }
        return {
          id: r.conversation_id,
          customer: "Клиент",
          initials: "К",
          agent: "Оператор",
          topic: "Импортированный диалог",
          channel: r.channel === "voice call" ? "call" : "chat",
          language: r.language,
          date: "Только что",
          duration: "—",
          status: "pending",
          score: null,
          messages,
          results: [],
          audio_url: audio,
        };
      });
      onImport(list);
    } catch (e) {
      setError(e.message);
    }
  }
  return (
    <div className="form">
      <p className="muted">
        Загрузите JSON, полученный из готового API. Поддерживается структура
        data.records. Подписанный URL в браузере не сохраняется.
      </p>
      <label className="upload-area">
        <Upload size={25} />
        <strong>Выберите JSON-файл</strong>
        <span>или вставьте ответ API ниже</span>
        <input
          type="file"
          accept=".json,application/json"
          onChange={async (e) => {
            const f = e.target.files[0];
            if (f) {
              if (f.size > 10 * 1024 * 1024) {
                setError("Максимальный размер файла — 10 МБ.");
                return;
              }
              setRaw(await f.text());
              setError("");
            }
          }}
        />
      </label>
      <label>
        Ответ API
        <textarea
          rows={6}
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          placeholder='{"data":{"records":[...]}}'
        />
      </label>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <div className="notice">
        <CircleHelp size={18} />
        <span>
          Импорт сохраняет транскрипты. Оценка моделью станет доступна после
          подключения серверной части.
        </span>
      </div>
      <Button primary onClick={parse} disabled={!raw.trim()}>
        <Upload size={16} />
        Импортировать
      </Button>
    </div>
  );
}
