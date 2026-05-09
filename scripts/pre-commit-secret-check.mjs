#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import { basename, resolve } from "node:path";
import { writeSafetyReport } from "./local-safety-report.mjs";

const repoRoot = resolve(process.cwd());
const maxScanBytes = 5 * 1024 * 1024;
const findings = {
  blockedPaths: [],
  payloadLogs: [],
  secrets: [],
};

const blockedRuntimeParts = new Set([
  ".cache",
  ".mypy_cache",
  ".next",
  ".nuxt",
  ".parcel-cache",
  ".playwright-cli",
  ".pytest_cache",
  ".ruff_cache",
  ".turbo",
  ".venv",
  "__pycache__",
  "backups",
  "build",
  "coverage",
  "data",
  "dist",
  "env",
  "exports",
  "htmlcov",
  "local_backups",
  "node_modules",
  "out",
  "playwright-report",
  "screenshots",
  "test-results",
  "tmp",
  "venv",
  "workspaces",
]);

const blockedRuntimeSuffixes = [
  ".log",
  ".pyc",
  ".pyo",
  ".sqlite",
  ".sqlite-journal",
  ".sqlite-shm",
  ".sqlite-wal",
];

const payloadLogPatterns = [
  /provider[-_ ]?payload/i,
  /provider[-_ ]?response/i,
  /provider[-_ ]?request/i,
  /provider[-_ ]?prompt/i,
  /raw[-_ ]?provider/i,
  /raw[-_ ]?prompt/i,
  /raw[-_ ]?response/i,
  /prompt[-_ ]?payload/i,
  /prompt[-_ ]?log/i,
  /payload[-_ ]?log/i,
  /ai[-_ ]?payload/i,
  /llm[-_ ]?payload/i,
];

const secretPatterns = [
  { name: "OpenAI-style API key", pattern: /\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b/ },
  { name: "DeepSeek API key assignment", pattern: /\bDEEPSEEK_API_KEY\s*=\s*["']?[A-Za-z0-9_-]{20,}/i },
  { name: "Authorization bearer token", pattern: /\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._-]{20,}/i },
  { name: "GitHub token", pattern: /\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b/ },
  { name: "GitHub fine-grained token", pattern: /\bgithub_pat_[A-Za-z0-9_]{30,}\b/ },
  { name: "AWS access key", pattern: /\bAKIA[0-9A-Z]{16}\b/ },
  { name: "Slack token", pattern: /\bxox[baprs]-[A-Za-z0-9-]{20,}\b/ },
];

const safePlaceholderMarkers = ["example", "fake", "local-only", "placeholder", "test", "your_"];
const safePlaceholderPrefixes = [
  "sk-deepseek-",
  "sk-live-",
  "sk-openai-",
  "sk-prototype-",
  "sk-release-",
  "sk-route-",
];

const trackedFiles = gitList(["ls-files", "-z"]);
const stagedFiles = gitList(["diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"]);
const filesToCheck = new Set([...trackedFiles, ...stagedFiles]);
const stagedSet = new Set(stagedFiles);

for (const file of [...filesToCheck].sort()) {
  const reason = blockedPathReason(file);
  if (reason === "payload-log") {
    findings.payloadLogs.push(file);
    continue;
  }
  if (reason) {
    findings.blockedPaths.push(`${file} (${reason})`);
    continue;
  }

  const content = await readCandidate(file, stagedSet.has(file));
  if (!content) {
    continue;
  }

  for (const { name, pattern } of secretPatterns) {
    if (hasNonPlaceholderSecret(pattern, content)) {
      findings.secrets.push(`${file} (${name})`);
      break;
    }
  }
}

const findingCount = findings.blockedPaths.length + findings.payloadLogs.length + findings.secrets.length;
await writeSafetyReport({
  secretScan: {
    status: findingCount ? "failed" : "passed",
    checkedFiles: filesToCheck.size,
    findings,
  },
});

if (findingCount) {
  console.error("Safety check failed.");
  printFindings("Tracked/staged blocked local paths", findings.blockedPaths);
  printFindings("Tracked/staged generated payload logs", findings.payloadLogs);
  printFindings("Obvious secret patterns found", findings.secrets);
  console.error("No secret values were printed. Remove these files from git tracking or replace real keys with safe placeholders.");
  process.exit(1);
}

console.log(`Safety check passed. Checked ${filesToCheck.size} tracked/staged file(s); no blocked local paths, generated payload logs, or obvious API keys found.`);

function gitList(args) {
  try {
    const output = execFileSync("git", args, {
      cwd: repoRoot,
      encoding: "buffer",
      stdio: ["ignore", "pipe", "ignore"],
    });
    return output.toString("utf8").split("\0").filter(Boolean);
  } catch {
    return [];
  }
}

async function readCandidate(file, preferStaged) {
  if (preferStaged) {
    try {
      const output = execFileSync("git", ["show", `:${file}`], {
        cwd: repoRoot,
        encoding: "buffer",
        maxBuffer: maxScanBytes,
        stdio: ["ignore", "pipe", "ignore"],
      });
      return decodeText(output);
    } catch {
      return "";
    }
  }

  try {
    return decodeText(await readFile(resolve(repoRoot, file)));
  } catch {
    return "";
  }
}

function decodeText(buffer) {
  if (buffer.length > maxScanBytes || buffer.subarray(0, Math.min(buffer.length, 8000)).includes(0)) {
    return "";
  }
  return buffer.toString("utf8");
}

function blockedPathReason(file) {
  const name = basename(file);
  const parts = file.split("/");
  if (isEnvFile(name)) {
    return "env-file";
  }
  if (isPayloadLog(file)) {
    return "payload-log";
  }
  if (parts.some((part) => blockedRuntimeParts.has(part))) {
    return "runtime-or-generated-path";
  }
  if (blockedRuntimeSuffixes.some((suffix) => name.endsWith(suffix))) {
    return "runtime-file";
  }
  return null;
}

function isEnvFile(name) {
  return name === ".env" || name.startsWith(".env.");
}

function isPayloadLog(file) {
  return payloadLogPatterns.some((pattern) => pattern.test(file));
}

function hasNonPlaceholderSecret(pattern, content) {
  const matches = content.match(new RegExp(pattern.source, pattern.flags.includes("g") ? pattern.flags : `${pattern.flags}g`));
  if (!matches) {
    return false;
  }
  return matches.some((match) => !isSafePlaceholderMatch(match));
}

function isSafePlaceholderMatch(value) {
  const normalized = value.toLowerCase();
  if (safePlaceholderMarkers.some((marker) => normalized.includes(marker))) {
    return true;
  }
  const tokenMatch = normalized.match(/sk-[a-z0-9_-]+/);
  return Boolean(tokenMatch && safePlaceholderPrefixes.some((prefix) => tokenMatch[0].startsWith(prefix)));
}

function printFindings(title, items) {
  if (!items.length) {
    return;
  }
  console.error(`${title}:`);
  for (const item of items.slice(0, 30)) {
    console.error(`- ${item}`);
  }
  if (items.length > 30) {
    console.error(`- ...and ${items.length - 30} more`);
  }
}
