const { createHash, timingSafeEqual } = require("node:crypto");

const MAX_BYTES = 4 * 1024 * 1024;
const TIMEOUT_MS = 55_000;
const METHODS = new Map([
  ["/api/health", ["GET"]],
  ["/api/workspace", ["GET", "PUT"]],
  ["/api/organizer", ["GET"]],
  ["/api/evaluate", ["POST"]],
]);

class ProxyError extends Error {
  constructor(status, detail) {
    super(detail);
    this.status = status;
  }
}

function reply(res, status, detail, headers = {}) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("X-Content-Type-Options", "nosniff");
  for (const [name, value] of Object.entries(headers))
    res.setHeader(name, value);
  res.end(JSON.stringify(detail));
}

function routeFor(req) {
  const raw = req.url || "";
  if (!raw.startsWith("/") || raw.startsWith("//") || raw.includes("\\")) {
    throw new ProxyError(404, "API-маршрут не найден.");
  }
  const rawPath = raw.split("?")[0];
  // Reject normalization tricks before URL can turn them into a different allowed route.
  if (/(?:^|\/)(?:\.|%2e){1,2}(?:\/|$)/i.test(rawPath)) {
    throw new ProxyError(404, "API-маршрут не найден.");
  }
  let url;
  try {
    url = new URL(raw, "https://cqa.invalid");
  } catch {
    throw new ProxyError(400, "Некорректный API-запрос.");
  }
  // Vercel rewrites can carry the matched route as an internal query parameter.
  const rewrite = url.searchParams.getAll("__cqa_path");
  if (rewrite.length) {
    const value = rewrite[0];
    if (
      rewrite.length !== 1 ||
      !value ||
      value.length > 512 ||
      value.includes("\\") ||
      /(?:^|\/)(?:\.|%2e){1,2}(?:\/|$)/i.test(value)
    ) {
      throw new ProxyError(404, "API-маршрут не найден.");
    }
    if (url.pathname === "/api/proxy") {
      url.pathname = "/api/" + value;
    } else {
      let matches = false;
      try {
        matches =
          decodeURIComponent(url.pathname.slice(5)) ===
          decodeURIComponent(value);
      } catch {
        /* Invalid encoding is rejected. */
      }
      if (!matches) throw new ProxyError(400, "Некорректный API-маршрут.");
    }
    url.searchParams.delete("__cqa_path");
  }
  let methods = METHODS.get(url.pathname);
  if (url.pathname.startsWith("/api/history/")) {
    let id;
    try {
      id = decodeURIComponent(url.pathname.slice("/api/history/".length));
    } catch {
      throw new ProxyError(400, "Некорректный ID диалога.");
    }
    if (!id || id.length > 200 || /[\u0000-\u001f\u007f]/.test(id)) {
      throw new ProxyError(400, "Некорректный ID диалога.");
    }
    methods = ["GET"];
  }
  if (!methods) throw new ProxyError(404, "API-маршрут не найден.");
  if (!methods.includes(req.method)) {
    const error = new ProxyError(
      405,
      "Метод не поддерживается этим API-маршрутом.",
    );
    error.allow = methods.join(", ");
    throw error;
  }
  if (url.pathname === "/api/organizer") {
    if (
      [...url.searchParams.keys()].some((key) => key !== "group_id") ||
      url.searchParams.getAll("group_id").length > 1 ||
      (url.searchParams.get("group_id") || "").length > 200
    ) {
      throw new ProxyError(400, "Допустим только один параметр group_id.");
    }
  } else if (url.search) {
    throw new ProxyError(
      400,
      "Этот API-маршрут не принимает параметры запроса.",
    );
  }
  return url.pathname + url.search;
}

function configuration() {
  const origin = process.env.CQA_BACKEND_URL;
  if (!origin) {
    throw new ProxyError(
      503,
      "Сервер AI-оценки ещё не подключён. Новые диалоги не оценены; интерфейс доступен в локальном режиме.",
    );
  }
  let url;
  try {
    url = new URL(origin);
  } catch {
    throw new ProxyError(
      503,
      "Подключение сервера оценки настроено некорректно.",
    );
  }
  if (
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.search ||
    url.hash
  ) {
    throw new ProxyError(
      503,
      "Подключение сервера оценки настроено некорректно.",
    );
  }
  const user = process.env.CQA_SITE_USER;
  const password = process.env.CQA_SITE_PASSWORD;
  const backendAuth = process.env.CQA_BACKEND_AUTH;
  if (
    !user ||
    !password ||
    user.includes(":") ||
    /[\r\n]/.test(user + password) ||
    password.length < 12
  ) {
    throw new ProxyError(
      503,
      "Для общей рабочей области не настроен защищённый вход.",
    );
  }
  if (backendAuth && /[\r\n]/.test(backendAuth)) {
    throw new ProxyError(
      503,
      "Подключение сервера оценки настроено некорректно.",
    );
  }
  return { origin: url.origin, user, password, backendAuth };
}

function authenticated(header, config) {
  let user = "";
  let password = "";
  if (
    typeof header === "string" &&
    /^Basic [A-Za-z0-9+/]+={0,2}$/i.test(header)
  ) {
    const credentials = Buffer.from(header.slice(6), "base64").toString("utf8");
    const separator = credentials.indexOf(":");
    if (separator >= 0) {
      user = credentials.slice(0, separator);
      password = credentials.slice(separator + 1);
    }
  }
  const digest = (value) => createHash("sha256").update(value).digest();
  const userMatches = timingSafeEqual(digest(user), digest(config.user));
  const passwordMatches = timingSafeEqual(
    digest(password),
    digest(config.password),
  );
  return userMatches && passwordMatches;
}

async function requestBody(req) {
  const contentLength = req.headers?.["content-length"];
  if (
    contentLength !== undefined &&
    (!/^\d+$/.test(String(contentLength)) || Number(contentLength) > MAX_BYTES)
  ) {
    throw new ProxyError(413, "Размер запроса превышает допустимые 4 МиБ.");
  }
  let data;
  if (req.body !== undefined) {
    try {
      data = Buffer.isBuffer(req.body)
        ? req.body
        : Buffer.from(
            typeof req.body === "string" ? req.body : JSON.stringify(req.body),
          );
    } catch {
      throw new ProxyError(
        400,
        "Тело запроса должно содержать корректный JSON.",
      );
    }
  } else if (req.readableEnded) {
    data = Buffer.alloc(0);
  } else {
    data = await new Promise((resolve, reject) => {
      const chunks = [];
      let length = 0;
      const cleanup = () => {
        req.off("data", onData);
        req.off("end", onEnd);
        req.off("error", onError);
        req.off("aborted", onAborted);
      };
      const onData = (chunk) => {
        const value = Buffer.from(chunk);
        length += value.length;
        if (length > MAX_BYTES) {
          cleanup();
          req.resume();
          reject(
            new ProxyError(413, "Размер запроса превышает допустимые 4 МиБ."),
          );
        } else chunks.push(value);
      };
      const onEnd = () => {
        cleanup();
        resolve(Buffer.concat(chunks));
      };
      const onError = () => {
        cleanup();
        reject(new ProxyError(400, "Не удалось прочитать запрос."));
      };
      const onAborted = () => {
        cleanup();
        reject(new ProxyError(400, "Передача запроса прервана."));
      };
      req.on("data", onData);
      req.on("end", onEnd);
      req.on("error", onError);
      req.on("aborted", onAborted);
    });
  }
  if (data.length > MAX_BYTES)
    throw new ProxyError(413, "Размер запроса превышает допустимые 4 МиБ.");
  if (req.method === "GET") {
    if (data.length)
      throw new ProxyError(400, "GET-запрос не должен содержать тело.");
    return undefined;
  }
  if (
    !/^application\/json(?:\s*;|$)/i.test(req.headers?.["content-type"] || "")
  ) {
    throw new ProxyError(
      415,
      "Для этого запроса требуется Content-Type: application/json.",
    );
  }
  try {
    JSON.parse(data.toString("utf8"));
  } catch {
    throw new ProxyError(400, "Тело запроса должно содержать корректный JSON.");
  }
  return data;
}

async function responseBody(response) {
  const reader = response.body?.getReader();
  if (!reader)
    throw new ProxyError(502, "Сервер оценки вернул некорректный ответ.");
  const chunks = [];
  let length = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    length += value.length;
    if (length > MAX_BYTES) {
      await reader.cancel();
      throw new ProxyError(502, "Ответ сервера превышает допустимый размер.");
    }
    chunks.push(Buffer.from(value));
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    throw new ProxyError(502, "Сервер оценки вернул некорректный ответ.");
  }
}

module.exports = async function cqaProxy(req, res) {
  let timer;
  let controller;
  try {
    const route = routeFor(req);
    const config = configuration();
    if (!authenticated(req.headers?.authorization, config)) {
      reply(
        res,
        401,
        { detail: "Войдите в защищённую рабочую область Freedom CQA." },
        {
          "WWW-Authenticate": 'Basic realm="Freedom CQA", charset="UTF-8"',
        },
      );
      return;
    }
    const body = await requestBody(req);
    const headers = { accept: "application/json" };
    if (body !== undefined) headers["content-type"] = "application/json";
    if (config.backendAuth) headers.authorization = config.backendAuth;
    controller = new AbortController();
    timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
    const response = await fetch(config.origin + route, {
      method: req.method,
      headers,
      body,
      signal: controller.signal,
      redirect: "manual",
    });
    if (!response.ok) {
      if (response.body) await response.body.cancel().catch(() => {});
      const status =
        response.status >= 400 && ![401, 403].includes(response.status)
          ? response.status
          : 502;
      throw new ProxyError(
        status,
        status === 409
          ? "Данные изменены другим участником. Экспортируйте изменения и обновите страницу."
          : "Сервис оценки временно недоступен или отклонил запрос. Повторите попытку позже.",
      );
    }
    reply(res, response.status, await responseBody(response));
  } catch (error) {
    if (controller?.signal.aborted) {
      reply(res, 504, {
        detail:
          "Сервер оценки не ответил за 55 секунд. Запрос прерван; оценка не подтверждена.",
      });
    } else if (error instanceof ProxyError) {
      reply(
        res,
        error.status,
        { detail: error.message },
        error.allow ? { Allow: error.allow } : {},
      );
    } else {
      // Never expose private origin URLs, provider errors, passwords or upstream auth.
      reply(res, 502, {
        detail:
          "Не удалось связаться с сервером оценки. Повторите попытку позже.",
      });
    }
  } finally {
    if (timer) clearTimeout(timer);
  }
};
