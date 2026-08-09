import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  VerificationError,
  changedFromSnapshot,
  changedFromBaseline,
  coverageEntry,
  digest,
  facts,
  loadJson,
  main,
  manifest,
  parse,
  reportFiles,
  snapshot,
  verify,
  verifyCoverage,
  verifyReports,
  changedLinesFromDiff,
  verifyChangedEntry,
} from "../../scripts/verify-changed-v8-branches.mjs";

const temporary: string[] = [];
afterEach(() => {
  vi.restoreAllMocks();
  for (const directory of temporary.splice(0)) fs.rmSync(directory, { recursive: true, force: true });
});

function temp() {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "phase31-v8-"));
  temporary.push(directory);
  return directory;
}

function coverage(
  file: string,
  source: string,
  { statement = 1, branch = 1 }: { statement?: number; branch?: number } = {},
) {
  fs.writeFileSync(file, JSON.stringify({ [source]: {
    inputSourceMap: { version: 3, sources: [source], mappings: "AAAA" },
    statementMap: { 0: { start: { line: 1 }, end: { line: 1 } } },
    branchMap: { 0: { line: 1, locations: [{ start: { line: 1 } }, { start: { line: 1 } }] } },
    s: { 0: statement },
    b: { 0: [branch, branch] },
  } }));
}

function vitestReport(
  file: string,
  test: string,
  { failed = 0, skipped = 0 }: { failed?: number; skipped?: number } = {},
) {
  fs.writeFileSync(file, JSON.stringify({
    numTotalTests: 1,
    numPassedTests: failed || skipped ? 0 : 1,
    numFailedTests: failed,
    numPendingTests: skipped,
    testResults: [{ filepath: test }],
  }));
}

function playwrightReport(file: string, test: string, status = "passed") {
  fs.writeFileSync(file, JSON.stringify({
    suites: [{
      file: test,
      specs: [{ tests: [{ results: [{ status }] }] }],
      suites: [{ file: "nested.spec.ts", specs: [] }],
    }],
  }));
}

describe("changed V8 verifier", () => {
  it("exposes only snapshot and verify subcommands", () => {
    expect(main(["other"])).toBe(1);
    expect(main([])).toBe(1);
  });

  it("rejects invalid baselines and snapshot overwrite", () => {
    expect(() => changedFromBaseline("")).toThrow(/required/);
    expect(() => changedFromBaseline("definitely-invalid")).toThrow(VerificationError);
    const directory = temp();
    const output = path.join(directory, "snapshot.json");
    fs.writeFileSync(output, "existing");
    expect(() => snapshot("unused", output)).toThrow(/already exists/);
  });

  it("hashes files and computes snapshot deltas", () => {
    const directory = temp();
    const source = path.join(directory, "source.ts");
    fs.writeFileSync(source, "export const value = 1;\n");
    expect(digest(source)).toMatch(/^[a-f0-9]{64}$/);
    expect(digest(path.join(directory, "missing.ts"))).toBeNull();
    const listed = facts(new Map([
      [path.relative(path.resolve(directory, "../../.."), source).replaceAll("\\", "/"), "M"],
      ["missing.ts", "D"],
    ]));
    expect(listed).toHaveLength(2);

    const snapshotPath = path.join(directory, "snapshot.json");
    fs.writeFileSync(snapshotPath, JSON.stringify({
      version: 1,
      baseline: "HEAD",
      files: [{ path: "frontend/scripts/verify-changed-v8-branches.mjs", sha256: "old" }],
    }));
    expect(changedFromSnapshot(snapshotPath).get("frontend/scripts/verify-changed-v8-branches.mjs")).toBeDefined();
    fs.writeFileSync(snapshotPath, JSON.stringify({ version: 2, files: [] }));
    expect(() => changedFromSnapshot(snapshotPath)).toThrow(/invalid start snapshot/);

    fs.writeFileSync(snapshotPath, JSON.stringify({
      version: 1,
      baseline: "HEAD",
      files: [{ path: "frontend/deleted-snapshot-file.ts", sha256: "old" }],
    }));
    expect(changedFromSnapshot(snapshotPath).get("frontend/deleted-snapshot-file.ts")).toBe("D");

    const cliSnapshot = path.join(directory, "cli-snapshot.json");
    expect(main(["snapshot", "--baseline", "HEAD", "--output", cliSnapshot])).toBe(0);
    expect(fs.existsSync(cliSnapshot)).toBe(true);
  });

  it("validates JSON, manifests, coverage entries, and report file discovery", () => {
    const directory = temp();
    const json = path.join(directory, "report.json");
    fs.writeFileSync(json, "bad json");
    expect(() => loadJson(json)).toThrow(/malformed/);
    const list = path.join(directory, "manifest.txt");
    fs.writeFileSync(list, "# only comment\n");
    expect(() => manifest(list)).toThrow(/empty/);
    expect(() => manifest(path.join(directory, "missing.txt"))).toThrow(/cannot read/);

    expect(coverageEntry({ "C:\\repo\\source.ts": { s: {} } }, "repo/source.ts")).toBeDefined();
    expect(() => coverageEntry({ "a/source.ts": {}, "b/source.ts": {} }, "source.ts")).toThrow(/ambiguous/);
    expect(reportFiles({
      testResults: [{ filepath: "a.test.ts" }, null],
      nested: { file: "b.spec.ts" },
      primitive: "ignored",
    })).toEqual(new Set(["a.test.ts", "b.spec.ts"]));
  });

  it("accepts complete coverage, membership, and execution reports", () => {
    const directory = temp();
    const source = "frontend/scripts/verify-changed-v8-branches.mjs";
    const test = "frontend/src/scripts/verify-changed-v8-branches.test.ts";
    const sourceManifest = path.join(directory, "source.txt");
    const testManifest = path.join(directory, "test.txt");
    const coverageJson = path.join(directory, "coverage.json");
    const vitestJson = path.join(directory, "vitest.json");
    const changedFiles = new Map([[source, "M"], [test, "M"]]);
    fs.writeFileSync(sourceManifest, `${source}\n`);
    fs.writeFileSync(testManifest, `${test}\n`);
    coverage(coverageJson, source);
    vitestReport(vitestJson, test);
    expect(() => verify({
      coverageJson,
      sourceManifest,
      testManifest,
      baseline: "HEAD",
      vitestJson: [vitestJson],
      changedFiles,
      changedLocations: new Map([[source, new Set([1])]]),
    })).not.toThrow();
  });

  it("rejects uncovered, absent, malformed, stale, dual, missing, failed, and skipped evidence", () => {
    const directory = temp();
    const source = "frontend/scripts/verify-changed-v8-branches.mjs";
    const test = "frontend/src/scripts/verify-changed-v8-branches.test.ts";
    const sourceManifest = path.join(directory, "source.txt");
    const testManifest = path.join(directory, "test.txt");
    const coverageJson = path.join(directory, "coverage.json");
    const vitestJson = path.join(directory, "vitest.json");
    const changedFiles = new Map([[source, "M"], [test, "M"]]);
    fs.writeFileSync(sourceManifest, `${source}\n`);
    fs.writeFileSync(testManifest, `${test}\n`);
    const baseline = process.env.PHASE31_BASELINE_SHA || "HEAD";
    coverage(coverageJson, source, { branch: 0 });
    vitestReport(vitestJson, test);
    expect(() => verify({ coverageJson, sourceManifest, testManifest, baseline, vitestJson: [vitestJson], changedFiles })).toThrow();
    coverage(coverageJson, "other.mjs");
    expect(() => verify({ coverageJson, sourceManifest, testManifest, baseline, vitestJson: [vitestJson], changedFiles })).toThrow(/absent/);
    fs.writeFileSync(coverageJson, "bad json");
    expect(() => verify({ coverageJson, sourceManifest, testManifest, baseline, vitestJson: [vitestJson], changedFiles })).toThrow(/malformed/);
    coverage(coverageJson, source);
    fs.writeFileSync(testManifest, `${source}\n${test}\n`);
    expect(() => verify({ coverageJson, sourceManifest, testManifest, baseline, vitestJson: [vitestJson], changedFiles })).toThrow(/dual/);
    fs.writeFileSync(testManifest, "frontend/scripts/stale.test.mjs\n");
    expect(() => verify({ coverageJson, sourceManifest, testManifest, baseline, vitestJson: [vitestJson], changedFiles })).toThrow();
    fs.writeFileSync(testManifest, `${test}\n`);
    vitestReport(vitestJson, "other.test.mjs");
    expect(() => verify({ coverageJson, sourceManifest, testManifest, baseline, vitestJson: [vitestJson], changedFiles })).toThrow(/not executed/);
    vitestReport(vitestJson, test, { failed: 1 });
    expect(() => verify({ coverageJson, sourceManifest, testManifest, baseline, vitestJson: [vitestJson], changedFiles })).toThrow(/zero fail\/skip/);
    vitestReport(vitestJson, test, { skipped: 1 });
    expect(() => verify({ coverageJson, sourceManifest, testManifest, baseline, vitestJson: [vitestJson], changedFiles })).toThrow(/zero fail\/skip/);
  });

  it("rejects missing and malformed Playwright reports and invalid option grammar", () => {
    const directory = temp();
    const malformed = path.join(directory, "playwright.json");
    fs.writeFileSync(malformed, JSON.stringify({ suites: "bad" }));
    expect(() => verifyReports([], [], new Set())).toThrow(/at least one/);
    expect(() => verifyReports([], [malformed], new Set())).toThrow(/malformed Playwright/);
    const playwright = path.join(directory, "playwright-valid.json");
    playwrightReport(playwright, "frontend/e2e/story.spec.ts");
    expect(() => verifyReports([], [playwright], new Set(["frontend/e2e/story.spec.ts"]))).not.toThrow();
    playwrightReport(playwright, "frontend/e2e/story.spec.ts", "skipped");
    expect(() => verifyReports([], [playwright], new Set())).toThrow(/zero fail\/skip/);
    playwrightReport(playwright, "frontend/e2e/story.spec.ts", "failed");
    expect(() => verifyReports([], [playwright], new Set())).toThrow(/zero fail\/skip/);

    const vitest = path.join(directory, "vitest.json");
    fs.writeFileSync(vitest, JSON.stringify({ numTotalTests: "bad" }));
    expect(() => verifyReports([vitest], [], new Set())).toThrow(/malformed Vitest/);
    vitestReport(vitest, "frontend/src/example.test.ts");
    expect(() => verifyReports([vitest], [], new Set(["frontend/src/example.test.ts"]))).not.toThrow();
    expect(() => verifyReports([vitest], [], new Set(["missing.test.ts"]))).toThrow(/not executed/);

    const coverageJson = path.join(directory, "coverage.json");
    fs.writeFileSync(coverageJson, "[]");
    expect(() => verifyCoverage(coverageJson, new Set(["source.ts"]))).toThrow(/not an object/);
    fs.writeFileSync(coverageJson, JSON.stringify({ "source.ts": { s: {}, b: {} } }));
    expect(() => verifyCoverage(
      coverageJson,
      new Set(["source.ts"]),
      new Map([["source.ts", new Set([1])]]),
    )).toThrow(/source map/);

    expect(() => parse(["verify", "--baseline", "HEAD", "--baseline", "HEAD"])).toThrow(/duplicate/);
    expect(() => parse(["verify", "--baseline"])).toThrow(/valueless/);
    expect(parse(["verify", "--vitest-json", "a", "--vitest-json", "b"]).values.get("--vitest-json")).toEqual(["a", "b"]);
    expect(main(["verify", "--unknown", "value"])).toBe(1);
    expect(main(["snapshot", "--baseline", "HEAD"])).toBe(1);
    expect(main(["verify", "--source-manifest", "x", "--test-manifest", "y", "--baseline", "HEAD"])).toBe(1);
    expect(main(["verify", "--coverage-json", "x", "--test-manifest", "y", "--baseline", "HEAD"])).toBe(1);
    expect(main(["verify", "--coverage-json", "x", "--source-manifest", "y", "--baseline", "HEAD"])).toBe(1);
    expect(main(["verify", "--coverage-json", "missing", "--source-manifest", "missing", "--test-manifest", "missing", "--baseline", "HEAD"])).toBe(1);
  });

  it("rejects invalid verifier identity and missing manifest paths", () => {
    const directory = temp();
    const sourceManifest = path.join(directory, "source.txt");
    const testManifest = path.join(directory, "tests.txt");
    const coverageJson = path.join(directory, "coverage.json");
    const report = path.join(directory, "vitest.json");
    fs.writeFileSync(sourceManifest, "frontend/scripts/verify-changed-v8-branches.mjs\n");
    fs.writeFileSync(testManifest, "frontend/src/scripts/verify-changed-v8-branches.test.ts\n");
    coverage(coverageJson, "frontend/scripts/verify-changed-v8-branches.mjs");
    vitestReport(report, "frontend/src/scripts/verify-changed-v8-branches.test.ts");
    const changedFiles = new Map([
      ["frontend/scripts/verify-changed-v8-branches.mjs", "M"],
      ["frontend/src/scripts/verify-changed-v8-branches.test.ts", "M"],
    ]);
    expect(() => verify({ coverageJson, sourceManifest, testManifest, vitestJson: [report], changedFiles })).toThrow(/exactly one/);
    expect(() => verify({ coverageJson, sourceManifest, testManifest, baseline: "HEAD", startSnapshot: "snapshot", vitestJson: [report], changedFiles })).toThrow(/exactly one/);
    fs.writeFileSync(testManifest, "frontend/src/scripts/missing.test.ts\n");
    expect(() => verify({ coverageJson, sourceManifest, testManifest, baseline: "HEAD", vitestJson: [report], changedFiles: new Map([["frontend/scripts/verify-changed-v8-branches.mjs", "M"], ["frontend/src/scripts/missing.test.ts", "M"]]) })).toThrow(/does not exist/);
  });

  it("parses moved lines and ignores deleted-only zero-context hunks", () => {
    const diff = `diff --git a/frontend/src/a.ts b/frontend/src/a.ts
--- a/frontend/src/a.ts
+++ b/frontend/src/a.ts
@@ -2,2 +2,0 @@
-const gone = 1;
-const removed = 2;
@@ -8 +6,2 @@
-const moved = false;
+const moved = true;
+const result = moved;
`;
    expect(changedLinesFromDiff(diff)).toEqual(new Map([["frontend/src/a.ts", new Set([6, 7])]]));
    expect(() => changedLinesFromDiff("@@ malformed @@\n")).toThrow(/malformed diff/);
    const contextDiff = `diff --git a/frontend/src/a.ts b/frontend/src/a.ts
--- a/frontend/src/a.ts
+++ b/frontend/src/a.ts
@@ -4 +4,2 @@
 unchanged
+const added = true;
\\ No newline at end of file
`;
    expect(changedLinesFromDiff(contextDiff)).toEqual(
      new Map([["frontend/src/a.ts", new Set([5])]]),
    );
    expect(() => changedLinesFromDiff(`+++ /dev/null
@@ -1 +1 @@
+const impossible = true;
`)).toThrow(/malformed diff hunk/);
  });

  it("requires source-map-aware changed statements and every changed branch arm", () => {
    const entry = {
      inputSourceMap: { version: 3, sources: ["feature.ts"], mappings: "AAAA" },
      statementMap: { "0": { start: { line: 6 }, end: { line: 6 } } },
      branchMap: { "0": { line: 6, locations: [{ start: { line: 6 } }, { start: { line: 7 } }] } },
      s: { "0": 1 },
      b: { "0": [1, 1] },
    };
    expect(() => verifyChangedEntry("frontend/src/feature.ts", entry, new Set([6, 7]))).not.toThrow();
    expect(() => verifyChangedEntry("frontend/src/feature.ts", { ...entry, s: { "0": 0 } }, new Set([6]))).toThrow(/uncovered changed statement/);
    expect(() => verifyChangedEntry("frontend/src/feature.ts", { ...entry, b: { "0": [1, 0] } }, new Set([7]))).toThrow(/uncovered changed branch/);
    expect(() => verifyChangedEntry("frontend/src/feature.ts", { ...entry, inputSourceMap: undefined }, new Set([6]))).toThrow(/source map/);
    expect(() => verifyChangedEntry(
      "frontend/src/feature.ts",
      { ...entry, statementMap: { "0": { start: { line: 8 }, end: { line: 7 } } } },
      new Set([8]),
    )).toThrow(/absent from coverage mapping/);
    expect(() => verifyChangedEntry(
      "frontend/src/feature.ts",
      { ...entry, statementMap: { "0": { start: {}, end: {} } } },
      new Set([6]),
    )).toThrow(/malformed statement mapping/);
    expect(() => verifyChangedEntry(
      "frontend/src/feature.ts",
      { ...entry, branchMap: { "0": { line: 6, locations: [] } } },
      new Set([6]),
    )).toThrow(/malformed branch mapping/);
  });

  it("discovers top-level report arrays and every supported executed-path form", () => {
    expect(reportFiles([
      { filepath: "a.test.ts" },
      { file: "nested/b.spec.ts" },
    ])).toEqual(new Set(["a.test.ts", "nested/b.spec.ts"]));

    const directory = temp();
    const report = path.join(directory, "vitest.json");
    for (const [reported, expected] of [
      ["frontend/src/example.test.ts", "frontend/src/example.test.ts"],
      ["C:/repo/frontend/src/example.test.ts", "frontend/src/example.test.ts"],
      ["C:/other/example.test.ts", "frontend/src/example.test.ts"],
    ] as const) {
      vitestReport(report, reported);
      expect(() => verifyReports([report], [], new Set([expected]))).not.toThrow();
    }
  });
});
