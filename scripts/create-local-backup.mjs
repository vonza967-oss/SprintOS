#!/usr/bin/env node

import { createReadStream, createWriteStream } from "node:fs";
import { opendir, lstat, mkdir, realpath, readFile, stat } from "node:fs/promises";
import { once } from "node:events";
import { basename, relative, resolve } from "node:path";
import { finished } from "node:stream/promises";
import { createGzip } from "node:zlib";
import { writeSafetyReport } from "./local-safety-report.mjs";

const repoRoot = await realpath(resolve(process.cwd()));
const backupDir = resolve(repoRoot, "local_backups");
const archiveName = `sprintos-local-backup-${timestamp()}.tar.gz`;
const archivePath = resolve(backupDir, archiveName);
const maxScanBytes = 5 * 1024 * 1024;

const blockedDirReasons = new Map([
  [".cache", "caches"],
  [".git", "gitInternals"],
  [".hg", "gitInternals"],
  [".mypy_cache", "caches"],
  [".next", "buildArtifacts"],
  [".nuxt", "buildArtifacts"],
  [".parcel-cache", "caches"],
  [".playwright-cli", "screenshots"],
  [".pytest_cache", "caches"],
  [".ruff_cache", "caches"],
  [".svn", "gitInternals"],
  [".turbo", "caches"],
  [".venv", "dependencies"],
  ["__pycache__", "caches"],
  ["backups", "backupRecursion"],
  ["build", "buildArtifacts"],
  ["coverage", "buildArtifacts"],
  ["data", "localState"],
  ["dist", "buildArtifacts"],
  ["env", "dependencies"],
  ["exports", "runtimeExports"],
  ["htmlcov", "buildArtifacts"],
  ["local_backups", "backupRecursion"],
  ["node_modules", "dependencies"],
  ["out", "buildArtifacts"],
  ["playwright-report", "screenshots"],
  ["screenshots", "screenshots"],
  ["test-results", "screenshots"],
  ["tmp", "caches"],
  ["venv", "dependencies"],
  ["workspaces", "runtimeExports"],
]);

const blockedFileNames = new Set([".DS_Store"]);
const blockedFileSuffixes = [
  ".log",
  ".pyc",
  ".pyo",
  ".sqlite",
  ".sqlite-journal",
  ".sqlite-shm",
  ".sqlite-wal",
  ".tar",
  ".tar.gz",
  ".tgz",
  ".zip",
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
  /\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b/,
  /\bDEEPSEEK_API_KEY\s*=\s*["']?[A-Za-z0-9_-]{20,}/i,
  /\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._-]{20,}/i,
  /\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b/,
  /\bgithub_pat_[A-Za-z0-9_]{30,}\b/,
  /\bAKIA[0-9A-Z]{16}\b/,
  /\bxox[baprs]-[A-Za-z0-9-]{20,}\b/,
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

const omitted = {
  envFiles: 0,
  gitInternals: 0,
  dependencies: 0,
  buildArtifacts: 0,
  caches: 0,
  screenshots: 0,
  runtimeExports: 0,
  localState: 0,
  backupRecursion: 0,
  payloadLogs: 0,
  secretMatches: 0,
  localNoise: 0,
  symlinks: 0,
};

await mkdir(backupDir, { recursive: true });

const entries = [];
await collectEntries(repoRoot, "", entries);

if (entries.length === 0) {
  throw new Error("No files were eligible for backup.");
}

await writeTarGz(entries, archivePath);
verifyArchiveEntryList(entries);

const archiveStats = await stat(archivePath);
const includedFiles = entries.filter((entry) => entry.kind === "file").length;

await writeSafetyReport({
  backup: {
    status: "passed",
    archivePath: relative(repoRoot, archivePath),
    archiveSizeBytes: archiveStats.size,
    includedFiles,
    omitted,
  },
});

console.log(`Backup created: ${relative(repoRoot, archivePath)}`);
console.log(`Archive size: ${formatBytes(archiveStats.size)}`);
console.log(`Included files: ${includedFiles}`);
console.log("Omitted files/folders:");
console.log(`- env files: ${omitted.envFiles}`);
console.log(`- git internals: ${omitted.gitInternals}`);
console.log(`- dependencies: ${omitted.dependencies}`);
console.log(`- build artifacts: ${omitted.buildArtifacts}`);
console.log(`- caches: ${omitted.caches}`);
console.log(`- screenshots: ${omitted.screenshots}`);
console.log(`- runtime exports/workspaces: ${omitted.runtimeExports}`);
console.log(`- local SQLite/runtime state: ${omitted.localState}`);
console.log(`- backup recursion: ${omitted.backupRecursion}`);
console.log(`- raw prompts/provider payloads: ${omitted.payloadLogs}`);
console.log(`- files with obvious secret patterns: ${omitted.secretMatches}`);
console.log(`- local noise/symlinks: ${omitted.localNoise + omitted.symlinks}`);
console.log("Verification passed: archive entries contain no blocked env files, git internals, dependencies, build outputs, caches, screenshots, generated payload logs, runtime state, local backups, or obvious secret paths.");

async function collectEntries(absDir, relDir, entries) {
  let dir;
  try {
    dir = await opendir(absDir);
  } catch {
    return;
  }

  for await (const dirent of dir) {
    const relPath = relDir ? `${relDir}/${dirent.name}` : dirent.name;
    const absPath = resolve(repoRoot, relPath);

    if (dirent.isSymbolicLink()) {
      omitted.symlinks += 1;
      continue;
    }

    const exclusion = exclusionFor(relPath, dirent.name);
    if (exclusion) {
      omitted[exclusion] += 1;
      continue;
    }

    if (dirent.isDirectory()) {
      entries.push({ kind: "directory", absPath, relPath, stats: await lstat(absPath) });
      await collectEntries(absPath, relPath, entries);
      continue;
    }

    if (dirent.isFile()) {
      if (await fileContainsSecret(absPath)) {
        omitted.secretMatches += 1;
        continue;
      }
      entries.push({ kind: "file", absPath, relPath, stats: await lstat(absPath) });
      continue;
    }

    omitted.localNoise += 1;
  }
}

function exclusionFor(relPath, name) {
  if (isEnvFile(name)) {
    return "envFiles";
  }
  if (isPayloadLogName(relPath)) {
    return "payloadLogs";
  }
  if (blockedFileNames.has(name) || blockedFileSuffixes.some((suffix) => name.endsWith(suffix))) {
    return "localNoise";
  }
  for (const part of relPath.split("/")) {
    if (blockedDirReasons.has(part)) {
      return blockedDirReasons.get(part);
    }
  }
  return null;
}

function isEnvFile(name) {
  return name === ".env" || name.startsWith(".env.");
}

function isPayloadLogName(name) {
  return payloadLogPatterns.some((pattern) => pattern.test(name));
}

async function fileContainsSecret(absPath) {
  let stats;
  try {
    stats = await lstat(absPath);
  } catch {
    return false;
  }
  if (!stats.isFile() || stats.size === 0 || stats.size > maxScanBytes) {
    return false;
  }
  let buffer;
  try {
    buffer = await readFile(absPath);
  } catch {
    return false;
  }
  if (buffer.subarray(0, Math.min(buffer.length, 8000)).includes(0)) {
    return false;
  }
  const text = buffer.toString("utf8");
  return secretPatterns.some((pattern) => hasNonPlaceholderSecret(pattern, text));
}

function hasNonPlaceholderSecret(pattern, text) {
  const flags = pattern.flags.includes("g") ? pattern.flags : `${pattern.flags}g`;
  const matches = text.match(new RegExp(pattern.source, flags));
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

async function writeTarGz(entries, destination) {
  const output = createWriteStream(destination, { mode: 0o600 });
  const gzip = createGzip({ level: 9 });
  gzip.pipe(output);

  for (const entry of entries) {
    await writeGzip(gzip, tarHeader(entry));
    if (entry.kind === "file") {
      await writeFileToGzip(gzip, entry.absPath);
      const padding = paddingFor(entry.stats.size);
      if (padding > 0) {
        await writeGzip(gzip, Buffer.alloc(padding));
      }
    }
  }

  await writeGzip(gzip, Buffer.alloc(1024));
  gzip.end();
  await finished(output);
}

async function writeFileToGzip(gzip, filePath) {
  const input = createReadStream(filePath);
  for await (const chunk of input) {
    await writeGzip(gzip, chunk);
  }
}

async function writeGzip(gzip, chunk) {
  if (!gzip.write(chunk)) {
    await once(gzip, "drain");
  }
}

function tarHeader(entry) {
  const header = Buffer.alloc(512, 0);
  const normalizedName = entry.kind === "directory" && !entry.relPath.endsWith("/")
    ? `${entry.relPath}/`
    : entry.relPath;
  const { name, prefix } = splitTarName(normalizedName);
  const mode = entry.kind === "directory" ? 0o755 : (entry.stats.mode & 0o777) || 0o644;
  const size = entry.kind === "file" ? entry.stats.size : 0;
  const mtime = Math.floor(entry.stats.mtimeMs / 1000);

  writeString(header, name, 0, 100);
  writeOctal(header, mode, 100, 8);
  writeOctal(header, 0, 108, 8);
  writeOctal(header, 0, 116, 8);
  writeOctal(header, size, 124, 12);
  writeOctal(header, mtime, 136, 12);
  header.fill(0x20, 148, 156);
  header[156] = entry.kind === "directory" ? "5".charCodeAt(0) : "0".charCodeAt(0);
  writeString(header, "ustar", 257, 6);
  writeString(header, "00", 263, 2);
  writeString(header, "sprintos", 265, 32);
  writeString(header, "sprintos", 297, 32);
  writeString(header, prefix, 345, 155);

  const checksum = header.reduce((sum, byte) => sum + byte, 0);
  writeOctal(header, checksum, 148, 8);
  return header;
}

function splitTarName(pathName) {
  if (Buffer.byteLength(pathName) <= 100) {
    return { name: pathName, prefix: "" };
  }
  const parts = pathName.split("/");
  for (let index = 1; index < parts.length; index += 1) {
    const prefix = parts.slice(0, index).join("/");
    const name = parts.slice(index).join("/");
    if (Buffer.byteLength(prefix) <= 155 && Buffer.byteLength(name) <= 100) {
      return { name, prefix };
    }
  }
  throw new Error(`Path is too long for portable tar format: ${pathName}`);
}

function writeString(buffer, value, offset, length) {
  buffer.write(value, offset, Math.min(Buffer.byteLength(value), length), "utf8");
}

function writeOctal(buffer, value, offset, length) {
  const text = value.toString(8).padStart(length - 1, "0").slice(0, length - 1);
  buffer.write(text, offset, length - 1, "ascii");
  buffer[offset + length - 1] = 0;
}

function paddingFor(size) {
  const remainder = size % 512;
  return remainder === 0 ? 0 : 512 - remainder;
}

function verifyArchiveEntryList(entries) {
  const violations = [];
  for (const entry of entries) {
    const relPath = entry.relPath;
    const parts = relPath.split("/");
    const name = basename(relPath);
    if (relPath.startsWith("/") || parts.includes("..")) violations.push(relPath);
    if (isEnvFile(name)) violations.push(relPath);
    if (isPayloadLogName(relPath)) violations.push(relPath);
    if (parts.some((part) => blockedDirReasons.has(part))) violations.push(relPath);
  }
  if (violations.length > 0) {
    throw new Error(`Backup verification failed; blocked paths were included: ${violations.slice(0, 10).join(", ")}`);
  }
}

function timestamp() {
  const now = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  return `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
