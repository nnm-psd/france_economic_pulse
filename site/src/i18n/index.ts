// Translation, formatting and URLs (D19). Shared by the pages (build time) and the chart script (browser).
import fr from "./fr.json";
import en from "./en.json";

export type Lang = "fr" | "en";
const dicts = { fr, en } as Record<Lang, Record<string, string>>;

// Fail the build if the two dictionaries drift apart.
const missing = [
  ...Object.keys(fr).filter((k) => !(k in en)).map((k) => `en.json lacks "${k}"`),
  ...Object.keys(en).filter((k) => !(k in fr)).map((k) => `fr.json lacks "${k}"`),
];
if (missing.length) throw new Error(`i18n: ${missing.join(", ")}`);

export function t(lang: Lang, key: string, vars: Record<string, string | number> = {}): string {
  const text = dicts[lang][key];
  if (text === undefined) throw new Error(`i18n: unknown key "${key}"`);
  return text.replace(/\{(\w+)\}/g, (_, name) => String(vars[name] ?? `{${name}}`));
}

const locale = (lang: Lang) => (lang === "fr" ? "fr-FR" : "en-GB");

/** "2026-09" -> "septembre 2026" / "September 2026" */
export function month(lang: Lang, m: string, style: "long" | "short" = "long"): string {
  const [y, mo] = m.split("-").map(Number);
  return new Intl.DateTimeFormat(locale(lang), { month: style, year: "numeric", timeZone: "UTC" }).format(Date.UTC(y, mo - 1, 1));
}

/** "2026-10-03" -> "3 octobre 2026" / "3 October 2026" */
export function day(lang: Lang, iso: string): string {
  const [y, mo, d] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat(locale(lang), { dateStyle: "long", timeZone: "UTC" }).format(Date.UTC(y, mo - 1, d));
}

/** 0.35 -> "+0,35 %" / "+0.35%" (value already in percent) */
export function pct(lang: Lang, v: number, digits = 1, signed = true): string {
  return new Intl.NumberFormat(locale(lang), {
    style: "percent",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    signDisplay: signed ? "exceptZero" : "auto",
  }).format(v / 100);
}

/** Latest data date for a source: monthly series show the month, daily ones the day. */
export const MONTHLY = new Set(["insee", "ecb"]);
export const latestDate = (lang: Lang, source: string, iso: string) => (MONTHLY.has(source) ? month(lang, iso.slice(0, 7)) : day(lang, iso));

export function num(lang: Lang, v: number, digits = 0): string {
  return new Intl.NumberFormat(locale(lang), { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(v);
}

// Same page in each language. Every internal link goes through url() so the GitHub Pages base path holds.
export const routes = {
  overview: { fr: "", en: "en/" },
  indicators: { fr: "indicateurs/", en: "en/indicators/" },
  model: { fr: "modele/", en: "en/model/" },
  methodology: { fr: "methodologie/", en: "en/methodology/" },
} as const;
export type Page = keyof typeof routes;

export function url(path: string): string {
  return `${import.meta.env.BASE_URL.replace(/\/$/, "")}/${path}`;
}

export const pageUrl = (page: Page, lang: Lang) => url(routes[page][lang]);
export const other = (lang: Lang): Lang => (lang === "fr" ? "en" : "fr");
