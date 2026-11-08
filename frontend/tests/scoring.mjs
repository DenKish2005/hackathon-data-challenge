// Cross-language scoring parity; no model calls or private data.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { scoreEvaluation } from "../src/data.js";

const root = fileURLToPath(new URL("../../", import.meta.url));
const cases = [];
for (const answer of [0, 1.005, 50.625, 99.995, 100])
  cases.push({
    criteria: [
      { id: "custom-scale", type: "scale", weight: 1, scale: [0, answer, 100] },
    ],
    results: [{ criterionId: "custom-scale", answer }],
  });
for (const weight of [1.005, 50.625, 99.995, 1e-7])
  cases.push({
    criteria: [
      { id: "custom-yes", type: "binary", weight },
      { id: "custom-no", type: "binary", weight: 100 - weight },
    ],
    results: [
      { criterionId: "custom-yes", answer: "Да" },
      { criterionId: "custom-no", answer: "Нет" },
    ],
  });
for (let index = 1; index <= 100; index++) {
  const criteria = [
    { id: "fraction", type: "scale", weight: index / 10, scale: [0, 1, 2, 3] },
    { id: "binary", type: "binary", weight: (101 - index) / 100 },
    { id: "optional", type: "binary", weight: 10, naAllowed: true },
    { id: "critical", type: "flag", weight: 0 },
  ];
  cases.push({
    criteria,
    results: [
      { criterionId: "fraction", answer: index % 3 },
      { criterionId: "binary", answer: index % 2 ? "Да" : "Нет" },
      { criterionId: "optional", answer: "N/A" },
      { criterionId: "critical", answer: index % 2 ? "Да" : "Нет" },
    ],
  });
}
cases.push({
  criteria: [{ id: "optional", type: "binary", weight: 10, naAllowed: true }],
  results: [{ criterionId: "optional", answer: "N/A" }],
});
cases.push({
  criteria: [{ id: "zero", type: "binary", weight: 0 }],
  results: [{ criterionId: "zero", answer: "Да" }],
});
const python =
  process.env.CQA_TEST_PYTHON ||
  path.join(
    root,
    ".venv",
    process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
  );
const baseline = spawnSync(
  python,
  [
    "-c",
    `
import json, sys
from types import SimpleNamespace as NS
from cqa.service import score
print(json.dumps([score([NS(**c) for c in x['criteria']], [NS(**r) for r in x['results']]) for x in json.load(sys.stdin)]))
`,
  ],
  {
    cwd: root,
    env: {
      ...process.env,
      PYTHONPATH: path.join(root, "src"),
      PYTHONUTF8: "1",
    },
    input: JSON.stringify(cases),
    encoding: "utf8",
  },
);
assert.equal(baseline.status, 0, baseline.error?.message || baseline.stderr);
const expected = JSON.parse(baseline.stdout);
cases.forEach((fixture, index) =>
  assert.deepEqual(
    scoreEvaluation(fixture.criteria, fixture.results),
    expected[index],
    `Decimal parity case ${index}`,
  ),
);
assert.equal(expected[1].score, 1.01);
assert.equal(scoreEvaluation(cases[0].criteria, []).incomplete, true);
assert.equal(
  scoreEvaluation(
    [{ id: "not-optional", type: "binary", weight: 1 }],
    [{ criterionId: "not-optional", answer: "N/A" }],
  ).incomplete,
  true,
);
console.log(
  `PASS: ${cases.length} frontend/server Decimal scoring comparisons, missing findings and forbidden N/A. No model calls.`,
);
