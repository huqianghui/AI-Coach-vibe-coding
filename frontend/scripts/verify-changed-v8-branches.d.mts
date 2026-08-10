export class VerificationError extends Error {}

export function changedFromBaseline(baseline: string): Map<string, string>;
export function changedFromSnapshot(file: string): Map<string, string>;
export function changedLinesFromDiff(diff: string): Map<string, Set<number>>;
export function coverageEntry(coverage: Record<string, unknown>, source: string): unknown;
export function digest(file: string): string | null;
export function facts(changed: Map<string, string>): Array<{
  path: string;
  status: string;
  sha256: string | null;
}>;
export function loadJson(file: string): unknown;
export function main(argv?: string[]): number;
export function manifest(file: string): Set<string>;
export function parse(argv: string[]): { command: string; values: Map<string, string | string[]> };
export function reportFiles(payload: unknown): Set<string>;
export function snapshot(baseline: string, output: string): void;
export function verifyChangedEntry(
  source: string,
  entry: Record<string, unknown>,
  changed: Set<number>,
): void;
export function verifyCoverage(
  file: string,
  sources: Set<string>,
  locations?: Map<string, Set<number>>,
): void;
export function verifyReports(vitestFiles: string[], playwrightFiles: string[], tests: Set<string>): void;
export function verify(options: {
  coverageJson: string;
  sourceManifest: string;
  testManifest: string;
  baseline?: string;
  startSnapshot?: string;
  vitestJson?: string[];
  playwrightJson?: string[];
  changedFiles?: Map<string, string>;
  changedLocations?: Map<string, Set<number>>;
}): void;