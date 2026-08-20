#!/usr/bin/env node
// Launcher only — no logic lives here. It runs the PyPI implementation,
// pinned to this package's own version, through uv's managed Python, so
// `npx pandoscope` and `uvx pandoscope` execute the same code.
"use strict";

const { spawnSync } = require("node:child_process");
const path = require("node:path");

const version = require("../package.json").version;

// The bundled `uv` npm dependency ships a launcher plus platform
// binaries; fall back to a PATH-installed uv when npm pruned it.
function uvInvocation() {
  try {
    const manifestPath = require.resolve("uv/package.json");
    const manifest = require(manifestPath);
    const rel =
      typeof manifest.bin === "string" ? manifest.bin : manifest.bin && manifest.bin.uv;
    if (rel) {
      const target = path.join(path.dirname(manifestPath), rel);
      return target.endsWith(".js")
        ? { command: process.execPath, prefix: [target] }
        : { command: target, prefix: [] };
    }
  } catch {
    // fall through to the PATH lookup
  }
  return { command: "uv", prefix: [] };
}

const { command, prefix } = uvInvocation();
const result = spawnSync(
  command,
  [
    ...prefix,
    "tool",
    "run",
    "--from",
    `pandoscope==${version}`,
    "pandoscope",
    ...process.argv.slice(2),
  ],
  { stdio: "inherit" },
);

if (result.error) {
  console.error(`pandoscope: could not launch uv (${result.error.message}).`);
  console.error(
    "Install uv (https://docs.astral.sh/uv/) or run the tool directly: uvx pandoscope",
  );
  process.exit(1);
}
process.exit(result.status === null ? 1 : result.status);
