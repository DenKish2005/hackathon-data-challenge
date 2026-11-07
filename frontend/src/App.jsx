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
import ReviewWorkspace from "./ReviewWorkspace";
import SelectionDesk from "./SelectionDesk";
import {
  initialCriteria,
  conversations as demoConversations,
  scoreEvaluation,
} from "./data";
const icons = {
  overview: LayoutDashboard,
  conversations: MessageCircle,
  criteria: SlidersHorizontal,
  agents: BookOpen,
  appeals: ShieldCheck,
};
const names = {
  conversations: "Диалоги",
  appeals: "Апелляции",
  overview: "Общая статистика",
  criteria: "Критерии оценки",
  agents: "Методика",
};
function stored(k, f) {
  try {
    const value = localStorage.getItem(k);
    const legacyKey = k.startsWith("freedom-cqa-")
      ? k.replace("freedom-cqa-", "sana-")
      : null;
    return (
      JSON.parse(
        value ?? (legacyKey ? localStorage.getItem(legacyKey) : null),
      ) ?? f
    );
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
  const [page, setPage] = useState("conversations"),
    [dialogs, setDialogs] = useState(() =>
      stored("freedom-cqa-dialogs", demoConversations),
    ),
    [criteria, setCriteria] = useState(() =>
      stored("freedom-cqa-criteria", initialCriteria),
    ),
    [version, setVersion] = useState(() => stored("freedom-cqa-version", 1)),
    [appeals, setAppeals] = useState(() => stored("freedom-cqa-appeals", []));
  const [selected, setSelected] = useState(null),
    [search, setSearch] = useState(""),
    [lang, setLang] = useState("Все языки"),
    [channel, setChannel] = useState("Все каналы"),
    [status, setStatus] = useState("Все статусы"),
    [modal, setModal] = useState(null),
    [toast, setToast] = useState(""),
    [mobile, setMobile] = useState(false),
    [period, setPeriod] = useState("Последние 7 оценок"),
    [sortKey, setSortKey] = useState("recent"),
    [queuePage, setQueuePage] = useState(1),
    [lastDialogId, setLastDialogId] = useState(null);
  useEffect(() => {
    localStorage.setItem("freedom-cqa-dialogs", JSON.stringify(dialogs));
  }, [dialogs]);
  useEffect(() => {
    localStorage.setItem("freedom-cqa-criteria", JSON.stringify(criteria));
    localStorage.setItem("freedom-cqa-version", JSON.stringify(version));
  }, [criteria, version]);
  useEffect(() => {
    localStorage.setItem("freedom-cqa-appeals", JSON.stringify(appeals));
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
    if (window.location.hash !== "#" + p)
      window.history.pushState(null, "", "#" + p);
  }
  function openDialog(dialog) {
    setSelected(dialog);
    setLastDialogId(dialog.id);
    setPage("conversations");
    const route = "#dialog/" + encodeURIComponent(dialog.id);
    if (window.location.hash !== route)
      window.history.pushState(null, "", route);
    window.scrollTo({ top: 0, behavior: "instant" });
  }
  useEffect(() => {
    const syncRoute = () => {
      const route = window.location.hash.slice(1);
      if (route.startsWith("dialog/")) {
        let id;
        try {
          id = decodeURIComponent(route.slice(7));
        } catch {
          return;
        }
        const found = dialogs.find((d) => d.id === id);
        if (found) {
          setSelected(found);
          setPage("conversations");
        } else {
          setSelected(null);
          setPage("conversations");
        }
      } else if (Object.hasOwn(names, route)) {
        setPage(route);
        setSelected(null);
      } else if (!route) {
        setPage("conversations");
        setSelected(null);
      }
    };
    syncRoute();
    window.addEventListener("popstate", syncRoute);
    window.addEventListener("hashchange", syncRoute);
    return () => {
      window.removeEventListener("popstate", syncRoute);
      window.removeEventListener("hashchange", syncRoute);
    };
  }, [dialogs]);
  const filtered = dialogs
    .filter(
      (d) =>
        (lang === "Все языки" || d.language === lang) &&
        (channel === "Все каналы" || d.channel === channel) &&
        (status === "Все статусы" ||
          (status === "critical" ? d.critical : d.status === status)) &&
        `${d.id} ${d.customer} ${d.agent} ${d.topic}`
          .toLowerCase()
          .includes(search.toLowerCase()),
    )
    .sort((a, b) =>
      sortKey === "low"
        ? (a.score ?? Infinity) - (b.score ?? Infinity)
        : sortKey === "high"
          ? (b.score ?? -1) - (a.score ?? -1)
          : 0,
    );
  const queuePages = Math.max(1, Math.ceil(filtered.length / 10));
  const visibleDialogs =
    page === "overview"
      ? filtered.slice(0, 5)
      : filtered.slice((queuePage - 1) * 10, queuePage * 10);
  useEffect(() => setQueuePage(1), [search, lang, channel, status, sortKey]);
  const reviewQueue =
    selected && filtered.some((d) => d.id === selected.id) ? filtered : dialogs;
  const reviewIndex = selected
    ? reviewQueue.findIndex((d) => d.id === selected.id)
    : -1;
  function closeDialog() {
    setSelected(null);
    setPage("conversations");
    window.history.pushState(null, "", "#conversations");
  }
  useEffect(() => {
    const shortcut = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k" && !modal) {
        e.preventDefault();
        if (page !== "conversations" || selected) navigate("conversations");
        requestAnimationFrame(() =>
          document.querySelector('[aria-label="Поиск диалогов"]')?.focus(),
        );
      }
    };
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, [modal, page, selected]);
  const evaluated = dialogs.filter(
      (d) => d.status !== "pending" && typeof d.score === "number",
    ),
    average = evaluated.length
      ? Math.round(
          evaluated.reduce((s, d) => s + d.score, 0) / evaluated.length,
        )
      : 0,
    openAppeals = appeals.filter((a) => a.status === "open");
  const criterionSummary = ["1", "2", "4", "5", "7"].map((id) => {
    const criterion = initialCriteria.find((c) => c.id === id);
    const values = evaluated.flatMap((d) => {
      const r = d.results?.find((r) => r.criterionId === id);
      if (!r || r.answer === "N/A") return [];
      const snapshot = (d.criteriaSnapshot || initialCriteria).find(
        (c) => c.id === id,
      );
      return snapshot?.type === "scale" && typeof r.answer === "number"
        ? [(r.answer / Math.max(...snapshot.scale)) * 100]
        : [r.answer === "Да" ? 100 : 0];
    });
    return {
      label:
        id === "4"
          ? "Корректность консультации"
          : id === "5"
            ? "Эмпатия"
            : criterion.title,
      v: values.length
        ? Math.round(values.reduce((a, b) => a + b, 0) / values.length)
        : 0,
    };
  });
  function exportData(target = null) {
    const chosen = target?.id ? target : null;
    const b = new Blob(
      [
        JSON.stringify(
          {
            demo: true,
            checklistVersion: chosen ? chosen.checklistVersion || 1 : version,
            criteria: chosen
              ? chosen.criteriaSnapshot || initialCriteria
              : criteria,
            conversations: chosen ? [chosen] : dialogs,
            appeals: chosen
              ? appeals.filter((a) => a.dialogId === chosen.id)
              : appeals,
          },
          null,
          2,
        ),
      ],
      { type: "application/json" },
    );
    const a = document.createElement("a");
    a.href = URL.createObjectURL(b);
    a.download = chosen
      ? `freedom-${chosen.id}-report.json`
      : "freedom-quality-report.json";
    a.click();
    URL.revokeObjectURL(a.href);
    setToast("Отчёт экспортирован в JSON");
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
      <a className="skip-link" href="#main-content">
        Перейти к содержимому
      </a>
      <aside className={"sidebar " + (mobile ? "mobile-open" : "")}>
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            navigate("conversations");
          }}
        >
          <span className="freedom-symbol" aria-hidden="true">
            <ShieldCheck size={27} />
          </span>
          <span className="freedom-wordmark">
            FREEDOM<span>BROKER</span>
          </span>
        </a>
        <div className="workspace">
          <span className="workspace-logo">
            <Activity size={18} />
          </span>
          <div>
            <strong>Контроль качества</strong>
            <small>Рабочее пространство</small>
          </div>
          <ChevronsUpDown size={15} />
        </div>
        <div className="nav-label">РАБОЧЕЕ ПРОСТРАНСТВО</div>
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
          <button
            className="nav-item"
            onClick={() => setModal({ type: "help" })}
          >
            <CircleHelp size={18} />
            <span>Как пользоваться</span>
            <ArrowUpRight size={14} />
          </button>
          <div className="profile">
            <Avatar name="Команда качества" />
            <div>
              <strong>Команда качества</strong>
              <small>Демонстрационный режим</small>
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
            <span>Freedom Broker</span>
            <ChevronRight size={14} />
            <strong>{selected ? selected.id : names[page]}</strong>
          </div>
          <div className="topbar-actions">
            <span className="demo-chip">
              <span />
              Демо-данные
            </span>
            <button
              className="search-shortcut"
              aria-label="Быстрый поиск — Ctrl K"
              onClick={() => {
                if (page !== "conversations" || selected)
                  navigate("conversations");
                requestAnimationFrame(() =>
                  document
                    .querySelector('[aria-label="Поиск диалогов"]')
                    ?.focus(),
                );
              }}
            >
              <Search size={14} />
              <kbd>Ctrl K</kbd>
            </button>
          </div>
        </header>
        <main id="main-content">
          {selected ? (
            <>
              <button className="back-link" onClick={closeDialog}>
                <ArrowLeft size={16} /> К списку диалогов
              </button>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">АНАЛИТИКА / {selected.id}</div>
                  <h1>{selected.topic}</h1>
                  <p>
                    {selected.id} <span className="dot-sep">•</span>{" "}
                    {selected.customer} <span className="dot-sep">•</span>{" "}
                    {selected.language} <span className="dot-sep">•</span>{" "}
                    {selected.duration}
                  </p>
                </div>
                <div className="dialogue-heading-tools">
                  <div className="review-pagination">
                    <button
                      className="icon-button"
                      aria-label="Предыдущий диалог"
                      disabled={reviewIndex <= 0}
                      onClick={() => openDialog(reviewQueue[reviewIndex - 1])}
                    >
                      <ArrowLeft size={16} />
                    </button>
                    <span>
                      {reviewIndex + 1} / {reviewQueue.length}
                    </span>
                    <button
                      className="icon-button"
                      aria-label="Следующий диалог"
                      disabled={
                        reviewIndex < 0 || reviewIndex >= reviewQueue.length - 1
                      }
                      onClick={() => openDialog(reviewQueue[reviewIndex + 1])}
                    >
                      <ArrowRight size={16} />
                    </button>
                  </div>
                  <select
                    aria-label="Выбрать другой диалог"
                    value={selected.id}
                    onChange={(e) =>
                      openDialog(dialogs.find((d) => d.id === e.target.value))
                    }
                  >
                    {dialogs.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.id} · {d.topic}
                      </option>
                    ))}
                  </select>
                  <Badge status={selected.status} />
                  <Button onClick={() => exportData(selected)}>
                    <ArrowDownToLine size={15} />
                    Отчёт
                  </Button>
                </div>
              </div>
              <ReviewWorkspace
                key={selected.id}
                dialog={selected}
                appeals={appeals.filter((a) => a.dialogId === selected.id)}
                onAppeal={(result) =>
                  setModal({ type: "appeal", dialog: selected, result })
                }
              />
            </>
          ) : (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">КОНТРОЛЬ КАЧЕСТВА</div>
                  <h1>
                    {page === "overview"
                      ? "Обзор качества"
                      : page === "conversations"
                        ? "Рабочее место контроля качества"
                        : names[page]}
                  </h1>
                  <p>
                    {page === "overview"
                      ? "Вся картина клиентского сервиса. От первого сообщения до результата."
                      : page === "conversations"
                        ? "Выберите диалог, проверьте оценку и найдите подтверждение в переписке."
                        : page === "criteria"
                          ? "Правила оценки, веса критериев и версии чек-листа."
                          : page === "agents"
                            ? "Применимость критериев, расчёт баллов и порядок пересмотра."
                            : "Обращения по спорным оценкам и решения проверяющих."}
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
                  ) : page === "appeals" ? (
                    <Button onClick={() => navigate("conversations")}>
                      Выбрать диалог <ArrowRight size={14} />
                    </Button>
                  ) : page === "agents" ? (
                    <Button onClick={() => navigate("criteria")}>
                      Открыть чек-лист <ArrowRight size={14} />
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
              {page === "conversations" && (
                <SelectionDesk
                  dialogs={dialogs}
                  initialCandidateId={lastDialogId}
                  criteria={criteria}
                  version={version}
                  onOpen={openDialog}
                  onEditCriterion={(criterion) =>
                    setModal({ type: "criterion", criterion })
                  }
                  onChecklist={() => navigate("criteria")}
                  onAppeal={(dialog, result) =>
                    setModal({ type: "appeal", dialog, result })
                  }
                />
              )}
              {page === "overview" && (
                <>
                  <div className="toolbar overview-toolbar">
                    <div className="segmented">
                      <button className="selected">Общая аналитика</button>
                      <button onClick={() => navigate("agents")}>
                        Методика оценки
                      </button>
                    </div>
                    <select
                      aria-label="Период аналитики"
                      value={period}
                      onChange={(e) => setPeriod(e.target.value)}
                    >
                      <option>Последние 7 оценок</option>
                      <option>Все оценки</option>
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
                      sparkline={evaluated
                        .slice(0, 8)
                        .reverse()
                        .map((d) => d.score)}
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
                          <h2>Качество диалогов</h2>
                          <p>Каждая оценка — часть общей картины</p>
                        </div>
                        <div className="chart-legend">
                          <span />
                          Оценка диалога
                          <i className="mean-marker" /> Среднее
                          <button
                            className="icon-button"
                            aria-label="Объяснение графика"
                            onClick={() =>
                              setToast(
                                "График построен по оценкам диалогов из текущего набора. Набор демонстрационный.",
                              )
                            }
                          >
                            <MoreHorizontal size={18} />
                          </button>
                        </div>
                      </div>
                      <Trend period={period} dialogs={evaluated} />
                      <div className="chart-foot">
                        <span>
                          <span className="tiny-star">✦</span> Рассчитано по
                          текущему набору
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
                      {criterionSummary.map((c, i) => (
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
                                background: c.v < 90 ? "#dba04b" : undefined,
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
                        По оценённым диалогам
                      </small>
                    </section>
                  </div>
                </>
              )}
              {page === "overview" && (
                <section className="panel table-panel">
                  {page === "conversations" && (
                    <div
                      className="queue-tabs"
                      role="group"
                      aria-label="Очередь диалогов"
                    >
                      {[
                        {
                          v: "Все статусы",
                          label: "Все диалоги",
                          count: dialogs.length,
                        },
                        {
                          v: "review",
                          label: "На проверке",
                          count: dialogs.filter((d) => d.status === "review")
                            .length,
                        },
                        {
                          v: "pending",
                          label: "Без оценки",
                          count: dialogs.filter((d) => d.status === "pending")
                            .length,
                        },
                        {
                          v: "critical",
                          label: "Грубые ошибки",
                          count: dialogs.filter((d) => d.critical).length,
                        },
                      ].map((t) => (
                        <button
                          key={t.v}
                          aria-pressed={status === t.v}
                          className={status === t.v ? "active" : ""}
                          onClick={() => setStatus(t.v)}
                        >
                          {t.label}
                          <span>{t.count}</span>
                        </button>
                      ))}
                    </div>
                  )}
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
                        aria-label="Сортировка"
                        value={sortKey}
                        onChange={(e) => setSortKey(e.target.value)}
                      >
                        <option value="recent">Сначала новые</option>
                        <option value="low">Оценка: по возрастанию</option>
                        <option value="high">Оценка: по убыванию</option>
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
                        {visibleDialogs.map((d) => (
                          <tr key={d.id} onClick={() => openDialog(d)}>
                            <td>
                              <button
                                className="dialog-button"
                                onClick={() => openDialog(d)}
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
                            <td className="score-cell">
                              {d.critical && (
                                <AlertTriangle
                                  size={13}
                                  className="critical-indicator"
                                  aria-label="Грубая ошибка"
                                />
                              )}
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
                              <button
                                className="analysis-row-action"
                                onClick={() => openDialog(d)}
                              >
                                Открыть <ArrowUpRight size={15} />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="mobile-dialog-list">
                    {visibleDialogs.map((d) => (
                      <button
                        className="mobile-dialog"
                        key={d.id}
                        onClick={() => openDialog(d)}
                        aria-label={`Открыть диалог ${d.id}: ${d.topic}`}
                      >
                        <span className="mobile-dialog-top">
                          <span className="mobile-dialog-id">
                            {d.id} · {d.language}
                          </span>
                          <Badge status={d.status} />
                        </span>
                        <span className="mobile-dialog-content">
                          <span>
                            <strong>{d.topic}</strong>
                            <small>{d.customer}</small>
                          </span>
                          <span
                            className={
                              "score " + (d.score >= 85 ? "high" : "mid")
                            }
                          >
                            {d.status === "pending" ? "—" : d.score}
                            <small>/100</small>
                            {d.critical && <AlertTriangle size={13} />}
                          </span>
                        </span>
                        <span className="mobile-dialog-bottom">
                          <span>
                            {d.agent} ·{" "}
                            {d.channel === "call" ? "Звонок" : "Чат"}
                          </span>
                          <ArrowUpRight size={14} />
                        </span>
                      </button>
                    ))}
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
                      Показано {visibleDialogs.length} из {filtered.length}{" "}
                      диалогов
                    </span>
                    {page === "conversations" && queuePages > 1 ? (
                      <div className="queue-pagination">
                        <button
                          className="icon-button"
                          aria-label="Предыдущая страница"
                          disabled={queuePage <= 1}
                          onClick={() => setQueuePage((p) => p - 1)}
                        >
                          <ArrowLeft size={14} />
                        </button>
                        <span>
                          {queuePage} / {queuePages}
                        </span>
                        <button
                          className="icon-button"
                          aria-label="Следующая страница"
                          disabled={queuePage >= queuePages}
                          onClick={() => setQueuePage((p) => p + 1)}
                        >
                          <ArrowRight size={14} />
                        </button>
                      </div>
                    ) : (
                      <span className="live-label">
                        <span />
                        Демонстрационный набор
                      </span>
                    )}
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
              {page === "agents" && <Methodology />}
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
                  <ShieldCheck size={14} /> Freedom Broker · Контроль качества
                </span>
                <span>Демо-данные · сохраняются в этом браузере</span>
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
                      ? "Как работает Freedom Quality"
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
              context={modal}
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
                    originalReason: modal.result.reason,
                    evidenceId: modal.result.evidenceId,
                    evidenceText:
                      modal.dialog.messages.find(
                        (m) => m.id === modal.result.evidenceId,
                      )?.text || "",
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
              dialog={dialogs.find((d) => d.id === modal.appeal.dialogId)}
              appeal={modal.appeal}
              onOpenDialog={() => {
                const d = dialogs.find((d) => d.id === modal.appeal.dialogId);
                openDialog(d);
                setModal(null);
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
              <Avatar name="Команда качества" />
              <h3>Команда качества</h3>
              <p>Freedom Broker · Демонстрационный режим</p>
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
function Stat({
  title,
  value,
  suffix,
  icon: Icon,
  note,
  green,
  orange,
  sparkline = [],
}) {
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
        {green && (
          <span className="stat-sparkline" aria-hidden="true">
            {sparkline.map((v, i) => (
              <i key={i} style={{ height: 4 + v * 0.21 }} />
            ))}
          </span>
        )}
      </div>
      <div className="stat-note">
        <span className={orange ? "orange-dot" : "green-dot"} />
        {note}
      </div>
    </article>
  );
}
function Trend({ period, dialogs }) {
  const rows = (period === "Все оценки" ? dialogs : dialogs.slice(0, 7))
    .slice()
    .reverse();
  const [active, setActive] = useState(null);
  const index = Math.min(active ?? rows.length - 1, rows.length - 1);
  const point = rows[index];
  const x = (i) => (rows.length > 1 ? 20 + (i * 660) / (rows.length - 1) : 350);
  const y = (value) => 180 - value * 1.6;
  const line = rows
    .map((d, i) => `${i ? "L" : "M"} ${x(i)} ${y(d.score)}`)
    .join(" ");
  const average = rows.length
    ? rows.reduce((a, d) => a + d.score, 0) / rows.length
    : 0;
  if (!rows.length)
    return (
      <div className="empty-state">
        <Activity />
        <p>Оценки появятся после обработки диалогов.</p>
      </div>
    );
  return (
    <div className="trend-chart">
      <div className="y-labels">
        {[100, 75, 50, 25, 0].map((v) => (
          <span key={v}>{v}</span>
        ))}
      </div>
      <div className="plot">
        <svg
          viewBox="0 0 700 190"
          preserveAspectRatio="none"
          role="img"
          aria-label="График оценок диалогов"
        >
          <defs>
            <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#75b92c" stopOpacity=".18" />
              <stop offset="100%" stopColor="#75b92c" stopOpacity=".01" />
            </linearGradient>
          </defs>
          {[20, 60, 100, 140, 180].map((yy) => (
            <line
              key={yy}
              x1="0"
              y1={yy}
              x2="700"
              y2={yy}
              stroke="#e9edeb"
              strokeDasharray="3 5"
            />
          ))}
          <path
            d={`${line} L ${x(rows.length - 1)} 190 L ${x(0)} 190 Z`}
            fill="url(#area)"
          />
          <line
            x1="0"
            y1={y(average)}
            x2="700"
            y2={y(average)}
            stroke="#adb8ad"
            strokeDasharray="5 5"
          />
          <path
            d={line}
            fill="none"
            stroke="#64aa26"
            strokeWidth="3"
            strokeLinejoin="round"
          />
          {rows.map((d, i) => (
            <g key={d.id}>
              <circle
                cx={x(i)}
                cy={y(d.score)}
                r={i === index ? 6 : 4}
                fill="white"
                stroke="#64aa26"
                strokeWidth={i === index ? 3 : 2}
              />
              <circle
                cx={x(i)}
                cy={y(d.score)}
                r="18"
                fill="transparent"
                tabIndex="0"
                role="button"
                aria-label={`${d.id}: ${d.score} баллов`}
                onMouseEnter={() => setActive(i)}
                onFocus={() => setActive(i)}
                onClick={() => setActive(i)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") setActive(i);
                }}
              />
            </g>
          ))}
        </svg>
        <div
          className="chart-tooltip"
          style={{
            left: `${Math.max(0, Math.min(70, (x(index) / 700) * 100 - 9))}%`,
          }}
        >
          <small>{point.id}</small>
          <strong>
            {point.score}
            <span> / 100</span>
          </strong>
        </div>
        <div className="x-labels">
          {rows.map((d) => (
            <span key={d.id}>#{d.id.split("-").at(-1)}</span>
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
function AppealForm({ onSubmit, context }) {
  const [comment, setComment] = useState("");
  return (
    <form
      className="form"
      onSubmit={(e) => {
        e.preventDefault();
        if (comment.trim()) onSubmit(comment.trim());
      }}
    >
      {context && (
        <div className="appeal-context">
          <span className="context-label">
            {context.dialog.id} · Оспариваемый критерий
          </span>
          <strong>
            {
              (context.dialog.criteriaSnapshot || initialCriteria).find(
                (c) => c.id === context.result.criterionId,
              )?.title
            }
          </strong>
          <span className="context-answer">
            Исходный ответ: {context.result.answer}
          </span>
          <p>{context.result.reason}</p>
          <blockquote>
            {context.dialog.messages.find(
              (m) => m.id === context.result.evidenceId,
            )?.text || "Подтверждающая реплика не указана"}
          </blockquote>
        </div>
      )}
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
function DecisionForm({ appeal, onSave, onOpenDialog, dialog }) {
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
      <div className="appeal-context">
        <span className="context-label">Основание исходной оценки</span>
        <p>
          {appeal.originalReason ||
            dialog?.results?.find((r) => r.criterionId === appeal.criterionId)
              ?.reason ||
            "Не указано"}
        </p>
        <blockquote>
          {appeal.evidenceText ||
            dialog?.messages?.find(
              (m) =>
                m.id ===
                (appeal.evidenceId ||
                  dialog?.results?.find(
                    (r) => r.criterionId === appeal.criterionId,
                  )?.evidenceId),
            )?.text ||
            "Реплика не указана"}
        </blockquote>
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

function Methodology() {
  return (
    <section className="panel methodology">
      <div className="section-intro">
        <h2>Как рассчитывается оценка</h2>
        <p>
          Каждый вывод связан с конкретным критерием и фрагментом разговора.
        </p>
      </div>
      <div className="methodology-steps">
        {[
          {
            n: "01",
            title: "Контекст разговора",
            text: "Учитываются запрос клиента, действия оператора и системные события. Сообщения бота служат контекстом.",
          },
          {
            n: "02",
            title: "Версия чек-листа",
            text: "Оценка связана с неизменяемой версией правил. Новый критерий применяется при новом запуске оценки.",
          },
          {
            n: "03",
            title: "Доказательства",
            text: "Для ответа указывается реплика. При пропуске действия — проверенный участок; при N/A — причина неприменимости.",
          },
          {
            n: "04",
            title: "Расчёт и пересмотр",
            text: "Баллы рассчитываются программно. После решения по апелляции итог пересчитывается, исходный результат сохраняется.",
          },
        ].map((x) => (
          <div key={x.n}>
            <span>{x.n}</span>
            <div>
              <h3>{x.title}</h3>
              <p>{x.text}</p>
            </div>
          </div>
        ))}
      </div>
      <div className="methodology-note">
        <strong>Правила расчёта</strong>
        <p>
          Итог = 100 × сумма (вес × доля оценки) / сумма применимых весов. N/A
          исключается из расчёта. Грубая ошибка отмечается отдельно и не
          обнуляет балл автоматически.
        </p>
        <code>Числовая оценка / максимум шкалы × вес критерия</code>
      </div>
      <p className="methodology-disclaimer">
        В прототипе используются демонстрационные оценки. Импортированные
        диалоги ожидают подключения серверного сервиса оценивания.
      </p>
    </section>
  );
}
