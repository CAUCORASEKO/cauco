import esbuild from "esbuild";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const directory = mkdtempSync(join(tmpdir(), "cauco-plugin-tests-"));
const obsidianStub = join(directory, "obsidian-stub.mjs");
writeFileSync(obsidianStub, "export const requestUrl = async () => { throw new Error('requestUrl should be injected in tests'); };\n");
const bundles = ["phase6c", "phase9a5", "phase10-dashboard"];

try {
  for (const name of bundles) {
    const bundle = join(directory, `${name}.test.mjs`);
    await esbuild.build({
    entryPoints: [`tests/${name}.test.ts`],
    bundle: true,
    format: "esm",
    platform: "node",
      target: "node22",
      alias: { obsidian: obsidianStub },
    outfile: bundle,
    logLevel: "warning",
    });
    const result = spawnSync(process.execPath, ["--test", bundle], { stdio: "inherit" });
    if (result.status !== 0) process.exitCode = result.status ?? 1;
  }
} finally {
  rmSync(directory, { recursive: true, force: true });
}
