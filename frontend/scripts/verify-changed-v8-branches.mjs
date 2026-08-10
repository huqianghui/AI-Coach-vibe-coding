/** Deterministic changed TS/TSX V8 coverage and test-execution gate. */

import { createHash, randomUUID } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

export class VerificationError extends Error {}

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const root = resolve(scriptDirectory, "../..");
const normalize = (value) => value.replaceAll("\\", "/").replace(/^\.\//, "");

function git(...args) {
  try {
    return execFileSync("git", ["-C", root, ...args], { encoding: "utf8" });
  } catch (error) {
    throw new VerificationError(error.stderr?.toString().trim() || "git command failed");
  }
}

export function changedFromBaseline(baseline) {
  if (!baseline) throw new VerificationError("baseline SHA is required");
  git("cat-file", "-e", `${baseline}^{commit}`);
  const changed = new Map();
  for (const line of git("diff", "--name-status", "--find-renames", baseline, "--").trim().split(/\r?\n/)) {
    if (!line) continue;
    const parts = line.split("\t");
    changed.set(normalize(parts.at(-1)), parts[0][0]);
  }
  for (const file of git("ls-files", "--others", "--exclude-standard").trim().split(/\r?\n/)) {
    if (file) changed.set(normalize(file), "A");
  }
  return changed;
}

export function changedLinesFromDiff(diff) {
  const changed = new Map();
  let current;
  let newLine;
  for (const line of diff.split(/\r?\n/)) {
    if (line.startsWith("+++ ")) {
      const target = line.slice(4);
      current = target === "/dev/null" ? undefined : normalize(target.replace(/^b\//, ""));
    } else if (line.startsWith("@@")) {
      const match = line.match(/^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
      if (!match || !current) throw new VerificationError(`malformed diff hunk: ${line}`);
      newLine = Number(match[1]);
    } else if (newLine !== undefined && current) {
      if (line.startsWith("+") && !line.startsWith("+++")) {
        if (!changed.has(current)) changed.set(current, new Set());
        changed.get(current).add(newLine++);
      } else if (line.startsWith("-") && !line.startsWith("---")) {
        // Deleted lines do not have an executable location in the new file.
      } else if (!line.startsWith("\\")) newLine++;
    }
  }
  return changed;
}

export function changedLines(baseline, sources) {
  const tracked = [...sources].filter((source) => git("ls-files", "--", source).trim());
  const result = tracked.length
    ? changedLinesFromDiff(git("diff", "--unified=0", "--no-ext-diff", baseline, "--", ...tracked))
    : new Map();
  for (const source of sources) if (!tracked.includes(source) && existsSync(join(root, source))) {
    result.set(source, new Set(readFileSync(join(root, source), "utf8").split(/\r?\n/).map((_, index) => index + 1)));
  }
  return result;
}

export function digest(file) {
  return existsSync(file) && statSync(file).isFile()
    ? createHash("sha256").update(readFileSync(file)).digest("hex")
    : null;
}

export function facts(changed) {
  return [...changed].sort(([a], [b]) => a.localeCompare(b)).map(([file, status]) => ({
    path: file,
    status,
    sha256: digest(join(root, file)),
  }));
}

export function snapshot(baseline, output) {
  if (existsSync(output)) throw new VerificationError(`snapshot already exists: ${output}`);
  mkdirSync(dirname(output), { recursive: true });
  const temporary = join(dirname(output), `.${basename(output)}.${process.pid}.${randomUUID()}`);
  writeFileSync(temporary, `${JSON.stringify({ version: 1, baseline, files: facts(changedFromBaseline(baseline)) }, null, 2)}\n`, { flag: "wx" });
  renameSync(temporary, output);
}

export function loadJson(file) {
  try {
    return JSON.parse(readFileSync(file, "utf8"));
  } catch (error) {
    throw new VerificationError(`malformed or unreadable JSON report: ${file}: ${error.message}`);
  }
}

export function manifest(file) {
  let entries;
  try {
    entries = new Set(readFileSync(file, "utf8").split(/\r?\n/).map((line) => normalize(line.trim())).filter((line) => line && !line.startsWith("#")));
  } catch (error) {
    throw new VerificationError(`cannot read manifest: ${file}: ${error.message}`);
  }
  if (!entries.size) throw new VerificationError(`manifest is empty: ${file}`);
  return entries;
}

export function changedFromSnapshot(file) {
  const payload = loadJson(file);
  if (payload.version !== 1 || !Array.isArray(payload.files)) throw new VerificationError("invalid start snapshot schema");
  const previous = new Map(payload.files.map((item) => [item.path, item.sha256]));
  const current = changedFromBaseline(payload.baseline);
  const currentFacts = new Map(facts(current).map((item) => [item.path, item.sha256]));
  const paths = new Set([...previous.keys(), ...currentFacts.keys()]);
  return new Map([...paths].filter((entry) => previous.get(entry) !== currentFacts.get(entry)).map((entry) => [entry, current.get(entry) || "D"]));
}

export function coverageEntry(coverage, source) {
  const sourceNormalized = normalize(source);
  const matches = Object.entries(coverage).filter(([key]) => {
    const candidate = normalize(key.startsWith("file:") ? fileURLToPath(key) : key);
    return candidate === sourceNormalized || candidate.endsWith(`/${sourceNormalized}`) || sourceNormalized.endsWith(`/${candidate}`);
  });
  if (matches.length > 1) throw new VerificationError(`ambiguous coverage entries for ${source}`);
  return matches[0]?.[1];
}

export function verifyChangedEntry(source, entry, changed) {
  if (!entry.inputSourceMap || !Array.isArray(entry.inputSourceMap.sources)) {
    throw new VerificationError(`source map missing for changed source: ${source}`);
  }
  if (!changed.size) throw new VerificationError(`changed source has no mapped diff locations: ${source}`);
  const mapped = new Set();
  for (const [id, location] of Object.entries(entry.statementMap || {})) {
    if (
      !Number.isInteger(location?.start?.line)
      || !Number.isInteger(location?.end?.line)
      || location.end.line < location.start.line
    ) {
      if (changed.has(location?.start?.line)) {
        throw new VerificationError(
          `changed executable locations absent from coverage mapping: ${source}:${location?.start?.line ?? "unknown"}`,
        );
      }
      throw new VerificationError(`malformed statement mapping: ${source}:${id}`);
    }
    const lines = [];
    for (let line = location.start.line; line <= location.end.line; line++) lines.push(line);
    lines.forEach((line) => mapped.add(line));
    if (lines.some((line) => changed.has(line))) {
      if ((entry.s || {})[id] <= 0) throw new VerificationError(`uncovered changed statement: ${source}:${location.start.line}`);
    }
  }
  for (const [id, branch] of Object.entries(entry.branchMap || {})) {
    const counts = (entry.b || {})[id];
    if (!Array.isArray(counts) || counts.length !== (branch.locations || []).length) {
      throw new VerificationError(`malformed branch mapping: ${source}:${branch.line || "unknown"}`);
    }
    branch.locations.forEach((location, index) => {
      const line = location.start.line;
      mapped.add(line);
      if (changed.has(line) || changed.has(branch.line)) {
        if (counts[index] <= 0) throw new VerificationError(`uncovered changed branch: ${source}:${line}:${index}`);
      }
    });
  }
  const executableLines = new Set([
    ...Object.values(entry.statementMap || {}).flatMap((location) => {
      const lines = [];
      for (let line = location.start.line; line <= location.end.line; line++) lines.push(line);
      return lines;
    }),
    ...Object.values(entry.branchMap || {}).flatMap((branch) => [
      branch.line,
      ...(branch.locations || []).map((location) => location.start.line),
    ]),
  ]);
  const absent = [...changed].filter((line) => executableLines.has(line) && !mapped.has(line));
  if (absent.length) throw new VerificationError(`changed executable locations absent from coverage mapping: ${source}:${absent.join(",")}`);
}

export function verifyCoverage(file, sources, locations = new Map()) {
  const coverage = loadJson(file);
  if (!coverage || Array.isArray(coverage) || typeof coverage !== "object") throw new VerificationError("coverage JSON is not an object");
  for (const source of [...sources].sort()) {
    const entry = coverageEntry(coverage, source);
    if (!entry) throw new VerificationError(`source absent from coverage: ${source}`);
    verifyChangedEntry(source, entry, locations.get(source) || new Set());
  }
}

export function reportFiles(payload) {
  const files = new Set();
  const visit = (value) => {
    if (!value || typeof value !== "object") return;
    if (typeof value.filepath === "string") files.add(normalize(value.filepath));
    if (typeof value.file === "string") files.add(normalize(value.file));
    if (Array.isArray(value)) value.forEach(visit);
    else Object.values(value).forEach(visit);
  };
  visit(payload);
  return files;
}

export function verifyReports(vitestFiles, playwrightFiles, tests) {
  if (!vitestFiles.length && !playwrightFiles.length) throw new VerificationError("at least one machine-readable test report is required");
  const executed = new Set();
  let passed = 0;
  let failed = 0;
  let skipped = 0;
  for (const file of vitestFiles) {
    const payload = loadJson(file);
    if (!Number.isInteger(payload.numTotalTests)) throw new VerificationError(`malformed Vitest report: ${file}`);
    passed += payload.numPassedTests || 0;
    failed += (payload.numFailedTests || 0) + (payload.numPendingTests || 0);
    skipped += payload.numPendingTests || 0;
    reportFiles(payload).forEach((entry) => executed.add(entry));
  }
  for (const file of playwrightFiles) {
    const payload = loadJson(file);
    if (!Array.isArray(payload.suites)) throw new VerificationError(`malformed Playwright report: ${file}`);
    const walk = (suite) => {
      if (suite.file) executed.add(normalize(suite.file));
      for (const spec of suite.specs || []) for (const test of spec.tests || []) for (const result of test.results || []) {
        if (result.status === "passed") passed += 1;
        else if (result.status === "skipped") skipped += 1;
        else failed += 1;
      }
      (suite.suites || []).forEach(walk);
    };
    payload.suites.forEach(walk);
  }
  if (passed <= 0 || failed || skipped) throw new VerificationError(`reports do not prove nonzero pass and zero fail/skip: passed=${passed}, failed=${failed}, skipped=${skipped}`);
  for (const test of tests) {
    if (![...executed].some((entry) => entry === test || entry.endsWith(`/${test}`) || entry.endsWith(`/${basename(test)}`))) {
      throw new VerificationError(`test manifest entry not executed: ${test}`);
    }
  }
}

export function verify({ coverageJson, sourceManifest, testManifest, baseline, startSnapshot, vitestJson = [], playwrightJson = [], changedFiles, changedLocations }) {
  if (Boolean(baseline) === Boolean(startSnapshot)) throw new VerificationError("provide exactly one of --baseline or --start-snapshot");
  const sources = manifest(sourceManifest);
  const tests = manifest(testManifest);
  const overlap = [...sources].filter((entry) => tests.has(entry));
  if (overlap.length) throw new VerificationError(`paths are dual-classified: ${overlap.join(", ")}`);
  const changed = changedFiles ?? (baseline ? changedFromBaseline(baseline) : changedFromSnapshot(startSnapshot));
  const changedTs = new Set([...changed].filter(([file, status]) => /(?<!\.d)\.(?:ts|tsx|mjs)$/.test(file) && status !== "D").map(([file]) => file));
  const classified = new Set([...sources, ...tests]);
  const missing = [...changedTs].filter((entry) => !classified.has(entry));
  const stale = [...classified].filter((entry) => !changedTs.has(entry));
  if (missing.length || stale.length) throw new VerificationError(`manifest membership mismatch; missing=${missing.join(",")}, stale=${stale.join(",")}`);
  for (const entry of classified) if (!existsSync(join(root, entry))) throw new VerificationError(`manifest path does not exist: ${entry}`);
  if (!baseline) throw new VerificationError("aggregate verification requires an explicit recorded baseline SHA");
  verifyCoverage(coverageJson, sources, changedLocations ?? changedLines(baseline, sources));
  verifyReports(vitestJson, playwrightJson, tests);
}

export function parse(argv) {
  const command = argv.shift();
  if (!command || !["snapshot", "verify"].includes(command)) throw new VerificationError("expected exactly one subcommand: snapshot or verify");
  const repeatable = new Set(["--vitest-json", "--playwright-json"]);
  const allowed = command === "snapshot"
    ? new Set(["--baseline", "--output"])
    : new Set(["--coverage-json", "--source-manifest", "--test-manifest", "--baseline", "--start-snapshot", ...repeatable]);
  const values = new Map();
  while (argv.length) {
    const flag = argv.shift();
    if (!allowed.has(flag) || !argv.length || argv[0].startsWith("--")) throw new VerificationError(`unknown or valueless option: ${flag}`);
    const value = argv.shift();
    if (repeatable.has(flag)) values.set(flag, [...(values.get(flag) || []), value]);
    else if (values.has(flag)) throw new VerificationError(`duplicate option: ${flag}`);
    else values.set(flag, value);
  }
  return { command, values };
}

export function main(argv = process.argv.slice(2)) {
  try {
    const { command, values } = parse([...argv]);
    if (command === "snapshot") {
      if (!values.get("--baseline") || !values.get("--output") || values.size !== 2) throw new VerificationError("snapshot requires --baseline and --output");
      snapshot(values.get("--baseline"), resolve(values.get("--output")));
    } else {
      for (const required of ["--coverage-json", "--source-manifest", "--test-manifest"]) if (!values.get(required)) throw new VerificationError(`verify requires ${required}`);
      verify({
        coverageJson: resolve(values.get("--coverage-json")),
        sourceManifest: resolve(values.get("--source-manifest")),
        testManifest: resolve(values.get("--test-manifest")),
        baseline: values.get("--baseline"),
        startSnapshot: values.get("--start-snapshot") && resolve(values.get("--start-snapshot")),
        vitestJson: values.get("--vitest-json")?.map((entry) => resolve(entry)) || [],
        playwrightJson: values.get("--playwright-json")?.map((entry) => resolve(entry)) || [],
      });
    }
    return 0;
  } catch (error) {
    console.error(`verification failed: ${error.message}`);
    return 1;
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) process.exitCode = main();
