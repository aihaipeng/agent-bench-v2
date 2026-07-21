import { readFile, writeFile } from "node:fs/promises";

import { build } from "esbuild";

const outputBase = "web/static/assets/workflow-canvas";

await build({
  entryPoints: ["web/frontend/workflow-canvas.jsx"],
  bundle: true,
  format: "iife",
  platform: "browser",
  target: "es2020",
  minify: true,
  legalComments: "linked",
  outfile: `${outputBase}.js`,
  logLevel: "info",
});

for (const path of [`${outputBase}.js`, `${outputBase}.css`, `${outputBase}.js.LEGAL.txt`]) {
  const content = await readFile(path, "utf8");
  const normalized = content.replace(/[ \t]+$/gm, "");
  if (normalized !== content) {
    await writeFile(path, normalized, "utf8");
  }
}
