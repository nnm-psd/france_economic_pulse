// Runs Lighthouse (mobile) on key pages of a running preview and fails below the D17 budget.
// Performance gets a lower floor in CI: shared runners are noisy; the 90 target is checked locally.
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

const ORIGIN = "http://localhost:4321/france_economic_pulse/";
const PAGES = ["", "en/", "indicateurs/", "modele/", "en/methodology/"];
const FLOOR = { performance: 0.8, accessibility: 0.95, "best-practices": 0.95, seo: 0.95 };

let failed = false;
for (const page of PAGES) {
  execFileSync("npx", ["--yes", "lighthouse@12", ORIGIN + page, "--quiet", "--chrome-flags=--headless=new --no-sandbox",
    "--output=json", "--output-path=lh.json"], { stdio: "inherit", shell: process.platform === "win32" });
  const scores = Object.fromEntries(Object.entries(JSON.parse(readFileSync("lh.json", "utf8")).categories).map(([k, c]) => [k, c.score]));
  const low = Object.entries(FLOOR).filter(([k, min]) => scores[k] < min);
  console.log(`${page || "home"}: ${Object.entries(scores).map(([k, v]) => `${k} ${Math.round(v * 100)}`).join(", ")}${low.length ? "  <- BELOW BUDGET" : ""}`);
  failed ||= low.length > 0;
}
process.exit(failed ? 1 : 0);
