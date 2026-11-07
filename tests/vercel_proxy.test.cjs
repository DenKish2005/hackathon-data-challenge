const { test, beforeEach, afterEach } = require("node:test");
const assert = require("node:assert/strict");
const { Readable } = require("node:stream");
const proxy = require("../api/[...path].js");

const KEYS = [
  "CQA_BACKEND_URL",
  "CQA_BACKEND_AUTH",
  "CQA_SITE_USER",
  "CQA_SITE_PASSWORD",
];
const SITE_USER = "reviewer";
const SITE_PASSWORD = "site-test-password-123";
const SITE_AUTH =
  "Basic " + Buffer.from(SITE_USER + ":" + SITE_PASSWORD).toString("base64");
let previous;
beforeEach(() => {
  previous = Object.fromEntries(KEYS.map((key) => [key, process.env[key]]));
  for (const key of KEYS) delete process.env[key];
});
afterEach(() => {
  for (const key of KEYS) {
    if (previous[key] === undefined) delete process.env[key];
    else process.env[key] = previous[key];
  }
});
function configured() {
  process.env.CQA_BACKEND_URL = "https://backend.private.example";
  process.env.CQA_BACKEND_AUTH = "Bearer server-secret-only";
  process.env.CQA_SITE_USER = SITE_USER;
  process.env.CQA_SITE_PASSWORD = SITE_PASSWORD;
}
function request(path, options = {}) {
  const req = Readable.from(options.chunks || []);
  req.url = path;
  req.method = options.method || "GET";
  req.headers = { authorization: SITE_AUTH, ...options.headers };
  if (Object.hasOwn(options, "body")) req.body = options.body;
  else if (!options.chunks) req.body = "";
  return req;
}
async function call(req) {
  const response = {
    headers: {},
    statusCode: 0,
    text: "",
    setHeader(key, value) {
      this.headers[key.toLowerCase()] = value;
    },
    end(value) {
      this.text = value;
    },
  };
  await proxy(req, response);
  response.json = JSON.parse(response.text);
  return response;
}
function noFetch(t) {
  return t.mock.method(globalThis, "fetch", () => {
    throw new Error("Unexpected upstream request");
  });
}

test("missing backend returns truthful503 JSON rather than a fake score or HTML", async (t) => {
  const fetch = noFetch(t);
  const response = await call(request("/api/health"));
  assert.equal(response.statusCode, 503);
  assert.match(response.json.detail, /ещё не подключён/);
  assert.equal(response.headers["cache-control"], "no-store");
  assert.match(response.headers["content-type"], /application\/json/);
  assert.equal(fetch.mock.callCount(), 0);
  assert.equal(Object.hasOwn(response.json, "score"), false);
});

test("backend configuration rejects non-HTTPS origins, embedded credentials, paths and queries", async (t) => {
  configured();
  const fetch = noFetch(t);
  for (const url of [
    "http://backend.private.example",
    "https://user:secret@backend.private.example",
    "https://backend.private.example/api",
    "https://backend.private.example/?token=secret",
    "https://backend.private.example/#private",
    "not a URL",
  ]) {
    process.env.CQA_BACKEND_URL = url;
    const response = await call(request("/api/health"));
    assert.equal(response.statusCode, 503);
    assert.equal(response.text.includes(url), false);
  }
  assert.equal(fetch.mock.callCount(), 0);
});

test("connecting a backend without protected site credentials remains unavailable", async (t) => {
  process.env.CQA_BACKEND_URL = "https://backend.private.example";
  const fetch = noFetch(t);
  assert.equal((await call(request("/api/workspace"))).statusCode, 503);
  assert.equal(fetch.mock.callCount(), 0);
});

test("missing, malformed or wrong site login gets401 before private workspace can be read", async (t) => {
  configured();
  const fetch = noFetch(t);
  for (const authorization of [
    undefined,
    "Bearer browser-token",
    "Basic invalid",
    "Basic " + Buffer.from(SITE_USER + ":wrong-password").toString("base64"),
  ]) {
    const response = await call(
      request("/api/workspace", { headers: { authorization } }),
    );
    assert.equal(response.statusCode, 401);
    assert.match(
      response.headers["www-authenticate"],
      /Basic realm="Freedom CQA"/,
    );
    assert.equal(response.headers["cache-control"], "no-store");
  }
  assert.equal(fetch.mock.callCount(), 0);
});

test("only fixed CQA paths and allowed methods can reach upstream", async (t) => {
  configured();
  const fetch = noFetch(t);
  const attempts = [
    ["/api/admin", "GET", 404],
    ["/api/health", "POST", 405],
    ["/api/evaluate", "GET", 405],
    ["/api/history/chat", "PUT", 405],
    ["https://attacker.invalid/api/health", "GET", 404],
    ["//attacker.invalid/api/health", "GET", 404],
    ["/api/history/%2e%2e/workspace", "GET", 404],
    ["/api/history/../workspace", "GET", 404],
    ["/api/history/a\\..\\workspace", "GET", 404],
    ["/api/organizer?url=https://attacker.invalid", "GET", 400],
    ["/api/workspace?token=private", "GET", 400],
  ];
  for (const [path, method, status] of attempts)
    assert.equal(
      (await call(request(path, { method }))).statusCode,
      status,
      path,
    );
  assert.equal(fetch.mock.callCount(), 0);
  const methodResponse = await call(
    request("/api/workspace", { method: "DELETE" }),
  );
  assert.equal(methodResponse.headers.allow, "GET, PUT");
});

test("valid site login forwards only the server backend authorization, never browser cookies", async (t) => {
  configured();
  let seen;
  t.mock.method(globalThis, "fetch", async (url, options) => {
    seen = { url, options };
    return new Response(
      JSON.stringify({ status: "ready", model: "real-backend-model" }),
    );
  });
  const response = await call(
    request("/api/health", {
      headers: {
        cookie: "private-browser-cookie",
        "x-forwarded-host": "attacker.invalid",
      },
    }),
  );
  assert.equal(response.statusCode, 200);
  assert.equal(response.json.model, "real-backend-model");
  assert.equal(seen.url, "https://backend.private.example/api/health");
  assert.deepEqual(seen.options.headers, {
    accept: "application/json",
    authorization: "Bearer server-secret-only",
  });
  assert.equal(seen.options.redirect, "manual");
  assert.equal(response.text.includes("server-secret-only"), false);
});

test("site credentials are never sent upstream when backend auth is not configured", async (t) => {
  configured();
  delete process.env.CQA_BACKEND_AUTH;
  let seen;
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    seen = options;
    return new Response("[]");
  });
  const response = await call(request("/api/history/chat-1"));
  assert.equal(response.statusCode, 200);
  assert.equal(Object.hasOwn(seen.headers, "authorization"), false);
});

test("workspace JSON, organizer group query and encoded history ID retain their meaning", async (t) => {
  configured();
  const seen = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    seen.push({ url, options });
    return new Response(JSON.stringify({ revision: 8 }));
  });
  const body = ' { "revision": 7, "data": {"note":"Клиент: проверка"} } ';
  assert.equal(
    (
      await call(
        request("/api/workspace", {
          method: "PUT",
          body,
          headers: { "content-type": "application/json; charset=utf-8" },
        }),
      )
    ).statusCode,
    200,
  );
  assert.equal(seen[0].options.body.toString("utf8"), body);
  assert.equal(seen[0].options.headers["content-type"], "application/json");
  await call(request("/api/organizer?group_id=DEV%20TEAM"));
  assert.equal(
    seen[1].url,
    "https://backend.private.example/api/organizer?group_id=DEV%20TEAM",
  );
  await call(request("/api/history/DEV%2Fchat%2F1"));
  assert.equal(
    seen[2].url,
    "https://backend.private.example/api/history/DEV%2Fchat%2F1",
  );
});

test("upstream errors and redirects cannot disclose private error bodies or move the proxy", async (t) => {
  configured();
  const privateError =
    "Bearer server-secret-only https://backend.private.example/private?token=private-password";
  for (const status of [302, 401, 403, 422, 503]) {
    t.mock.method(
      globalThis,
      "fetch",
      async () =>
        new Response(privateError, {
          status,
          headers: { location: "https://attacker.invalid/private" },
        }),
    );
    const response = await call(request("/api/health"));
    assert.ok(response.statusCode >= 400);
    assert.equal(response.text.includes("server-secret-only"), false);
    assert.equal(response.text.includes("backend.private.example"), false);
    assert.equal(response.text.includes("private-password"), false);
    assert.equal(Object.hasOwn(response.headers, "location"), false);
  }
});

test("workspace conflict preserves actionable recovery without disclosing upstream details", async (t) => {
  configured();
  t.mock.method(
    globalThis,
    "fetch",
    async () =>
      new Response(
        "private conflict at https://backend.private.example/db?token=server-secret-only",
        { status: 409 },
      ),
  );
  const response = await call(
    request("/api/workspace", {
      method: "PUT",
      body: { revision: 1, data: { dialogs: [] } },
      headers: { "content-type": "application/json" },
    }),
  );
  assert.equal(response.statusCode, 409);
  assert.equal(
    response.json.detail,
    "Данные изменены другим участником. Экспортируйте изменения и обновите страницу.",
  );
  assert.equal(
    /backend\.private|server-secret-only|private conflict/.test(response.text),
    false,
  );
  assert.equal(response.headers["cache-control"], "no-store");
});

test("network failures do not leak provider URL or authentication", async (t) => {
  configured();
  t.mock.method(globalThis, "fetch", async () => {
    throw new Error(
      "https://backend.private.example server-secret-only private-password",
    );
  });
  const response = await call(request("/api/health"));
  assert.equal(response.statusCode, 502);
  assert.equal(
    /backend\.private|server-secret|private-password/.test(response.text),
    false,
  );
});

test("oversized parsed, declared and streamed request bodies are rejected before upstream", async (t) => {
  configured();
  const fetch = noFetch(t);
  const huge = Buffer.alloc(4 * 1024 * 1024 + 1, 32);
  const options = [
    { body: huge },
    { body: "{}", headers: { "content-length": String(huge.length) } },
    {
      chunks: [
        huge.subarray(0, 2 * 1024 * 1024),
        huge.subarray(2 * 1024 * 1024),
      ],
    },
  ];
  for (const option of options) {
    const response = await call(
      request("/api/evaluate", {
        ...option,
        method: "POST",
        headers: { "content-type": "application/json", ...option.headers },
      }),
    );
    assert.equal(response.statusCode, 413);
  }
  assert.equal(fetch.mock.callCount(), 0);
});

test("malformed JSON and non-JSON writes fail visibly without reaching the backend", async (t) => {
  configured();
  const fetch = noFetch(t);
  assert.equal(
    (
      await call(
        request("/api/evaluate", {
          method: "POST",
          body: "{broken",
          headers: { "content-type": "application/json" },
        }),
      )
    ).statusCode,
    400,
  );
  assert.equal(
    (
      await call(
        request("/api/workspace", {
          method: "PUT",
          body: "{}",
          headers: { "content-type": "text/plain" },
        }),
      )
    ).statusCode,
    415,
  );
  assert.equal(fetch.mock.callCount(), 0);
});

test("55-second timeout actually aborts fetch and returns504 without inventing a result", async (t) => {
  configured();
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let started;
  let signal;
  const fetching = new Promise((resolve) => {
    started = resolve;
  });
  t.mock.method(
    globalThis,
    "fetch",
    (_url, options) =>
      new Promise((_resolve, reject) => {
        signal = options.signal;
        signal.addEventListener(
          "abort",
          () => reject(new DOMException("private timeout", "AbortError")),
          { once: true },
        );
        started();
      }),
  );
  const pending = call(request("/api/health"));
  await fetching;
  t.mock.timers.tick(55_000);
  const response = await pending;
  assert.equal(signal.aborted, true);
  assert.equal(response.statusCode, 504);
  assert.match(response.json.detail, /оценка не подтверждена/);
  assert.equal(Object.hasOwn(response.json, "score"), false);
});

test("HTML or oversized successful upstream responses are not served as API JSON", async (t) => {
  configured();
  t.mock.method(
    globalThis,
    "fetch",
    async () => new Response("<html>private-error</html>"),
  );
  assert.equal((await call(request("/api/health"))).statusCode, 502);
  t.mock.method(
    globalThis,
    "fetch",
    async () => new Response('"' + "a".repeat(4 * 1024 * 1024) + '"'),
  );
  assert.equal((await call(request("/api/health"))).statusCode, 502);
});
