import esbuild from "esbuild";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const directory = mkdtempSync(join(tmpdir(), "cauco-plugin-tests-"));
const bundle = join(directory, "phase6c.test.mjs");

try {
  await esbuild.build({
    entryPoints: ["tests/phase6c.test.ts"],
    bundle: true,
    format: "esm",
    platform: "node",
    target: "node22",
    outfile: bundle,
    logLevel: "warning",
  });
  const result = spawnSync(process.execPath, ["--test", bundle], { stdio: "inherit" });
  process.exitCode = result.status ?? 1;
} finally {
  rmSync(directory, { recursive: true, force: true });
}
