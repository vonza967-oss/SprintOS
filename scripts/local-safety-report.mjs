import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

export const safetyReportPath = resolve(process.cwd(), "public/dev/safety-report.json");

export const ignoredPathCoverage = [
  {
    label: ".env*",
    status: "covered",
    backupRule: "envFiles",
    safetyRule: "blocked-env",
    gitignore: [".env", ".env.*"],
  },
  {
    label: "dist/ and build/",
    status: "covered",
    backupRule: "buildArtifacts",
    safetyRule: "blocked-runtime",
    gitignore: ["dist/", "build/"],
  },
  {
    label: "cache folders",
    status: "covered",
    backupRule: "caches",
    safetyRule: "blocked-runtime",
    gitignore: [".cache/", ".pytest_cache/", ".turbo/", "node_modules/"],
  },
  {
    label: "screenshots",
    status: "covered",
    backupRule: "screenshots",
    safetyRule: "blocked-runtime",
    gitignore: [".playwright-cli/", "screenshots/"],
  },
  {
    label: "generated payload logs",
    status: "covered",
    backupRule: "payloadLogs",
    safetyRule: "blocked-payload-log",
    gitignore: ["*provider-payload*", "*raw-response*", "*payload-log*"],
  },
];

export async function writeSafetyReport(update) {
  const existing = await readReport();
  const report = {
    ignoredPathCoverage,
    ...existing,
    ...update,
    generatedAt: new Date().toISOString(),
    ignoredPathCoverage,
  };
  await mkdir(dirname(safetyReportPath), { recursive: true });
  await writeFile(safetyReportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  return report;
}

async function readReport() {
  try {
    return JSON.parse(await readFile(safetyReportPath, "utf8"));
  } catch {
    return {
      generatedAt: null,
      ignoredPathCoverage,
      secretScan: {
        status: "not-run",
        checkedFiles: 0,
        findings: [],
      },
      backup: {
        status: "not-run",
        archivePath: null,
      },
    };
  }
}
