#!/usr/bin/env node

import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(scriptDir, "..");
const args = process.argv.slice(2);

if (!args.includes("--confirm-live-provider")) {
  console.error("Refusing to run live provider acceptance without --confirm-live-provider.");
  process.exit(2);
}

if (process.env.NODE_ENV === "test" || process.env.SPRINTOS_TEST_MODE === "true") {
  console.error("Refusing to run live provider acceptance from a test environment.");
  process.exit(2);
}

const pythonScript = resolve(scriptDir, "live_app_generation_acceptance.py");
const python = process.env.PYTHON || "python3";
const child = spawn(python, [pythonScript, ...args], {
  cwd: repoRoot,
  env: process.env,
  stdio: "inherit",
});

child.on("error", (error) => {
  console.error(`Unable to start live provider acceptance: ${error.message}`);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    console.error(`Live provider acceptance stopped by signal ${signal}.`);
    process.exit(1);
  }
  process.exit(code ?? 1);
});
