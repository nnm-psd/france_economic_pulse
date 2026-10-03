// Symbols, formulas and source excerpts for the model page. Formulas are language-neutral TeX;
// the numbers inside them come from site.json, so the page always matches the model that ran.
import featuresPy from "../../pipeline/features.py?raw";
import modelPy from "../../pipeline/model.py?raw";
import { num, type Lang } from "./i18n";

/** Symbol and publication lag of each model input, in FEATURES order (pipeline/features.py). */
export const FEATURE_INFO: Record<string, { tex: string; known: string }> = {
  y_lag2: { tex: "y_{t-2}", known: "t-2" },
  elec: { tex: "\\Delta e_t", known: "t" },
  elec_lag1: { tex: "\\Delta e_{t-1}", known: "t" },
  climate: { tex: "c_t - 100", known: "t" },
  climate_chg: { tex: "\\Delta c_t", known: "t" },
  insolv_yoy: { tex: "\\Delta_{12}\\, n_t", known: "t" },
  spread_lag1: { tex: "s_{t-1}", known: "t-1" },
  spread_chg_lag1: { tex: "\\Delta s_{t-1}", known: "t-1" },
};

/** A number for use inside TeX: French decimal comma without the extra space TeX adds after commas. */
export function texNum(lang: Lang, v: number, digits: number): string {
  const s = num(lang, v, digits).replace(/[−-]/, "-").replace(",", "{,}").replace(/[  ]/g, "\\,");
  return v < 0 ? `{${s}}` : s; // braces keep a leading minus as a sign, not a subtraction
}

/**
 * A top-level `def name` or `NAME =` block from a Python file, so the page shows the code that actually runs.
 * Stops at the next line that starts in column 0 (closing brackets excepted).
 */
function excerpt(source: string, name: string): string {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const start = lines.findIndex((l) => l.startsWith(`def ${name}(`) || l.startsWith(`${name} =`));
  if (start < 0) throw new Error(`model page: "${name}" not found in the pipeline source`);
  let end = start + 1;
  while (end < lines.length && (lines[end] === "" || /^[\s)\]}]/.test(lines[end]))) end++;
  while (lines[end - 1] === "") end--;
  return lines.slice(start, end).join("\n");
}

const repo = "https://github.com/nnm-psd/france_economic_pulse/blob/main/pipeline";
export const EXCERPTS = {
  weather: { file: "features.py", url: `${repo}/features.py`, code: excerpt(featuresPy, "corrected_electricity") },
  models: { file: "model.py", url: `${repo}/model.py`, code: [excerpt(modelPy, "RIDGE_ALPHAS"), excerpt(modelPy, "MODELS")].join("\n") },
  training: { file: "model.py", url: `${repo}/model.py`, code: excerpt(modelPy, "training_rows") },
  explain: { file: "model.py", url: `${repo}/model.py`, code: excerpt(modelPy, "explain") },
};
