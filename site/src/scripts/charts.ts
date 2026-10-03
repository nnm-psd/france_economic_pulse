// Draws every <figure data-chart> on the page with Observable Plot (D14).
// Specs follow the dataviz skill: 2px lines, >=8px end dots with a surface ring, hairline grid,
// text in ink tokens (never series colours), crosshair tooltip, table view in the page.
import * as Plot from "@observablehq/plot";
import { month, num, pct, type Lang } from "../i18n";

type Point = { m: string; v: number };
type Spec =
  | { kind: "level"; lang: Lang; ipi: Point[]; nowcast: { m: string; level: number; level_lo: number; level_hi: number; g: number; lo: number; hi: number }[]; labels: Record<string, string> }
  | { kind: "line"; lang: Lang; series: Point[]; digits: number; reference?: number }
  | { kind: "backtest"; lang: Lang; rows: { m: string; actual: number; ridge: number }[]; labels: Record<string, string> }
  | { kind: "contrib"; lang: Lang; rows: { label: string; v: number }[] };

const date = (m: string) => new Date(Date.UTC(+m.slice(0, 4), +m.slice(5, 7) - 1, 1));
const iso = (d: Date) => d.toISOString().slice(0, 7);
// Colour tokens, read once per draw (reading styles per mark forces extra layout work).
let tokens: CSSStyleDeclaration;
const css = (name: string) => tokens.getPropertyValue(name).trim();
const colon = (lang: Lang) => (lang === "fr" ? " : " : ": "); // French puts a narrow space before ":"

function frame(lang: Lang, width: number, height: number, yFormat: (v: number) => string, extra: Plot.Markish[], years = false) {
  // Multi-year charts label years only; month labels would collide.
  const short = years ? (d: Date) => String(d.getUTCFullYear()) : (d: Date) => month(lang, iso(d), "short");
  return Plot.plot({
    width,
    height,
    marginLeft: 44,
    marginRight: width < 480 ? 16 : 96, // room for end labels
    style: { fontFamily: css("--font"), fontSize: "13px", color: css("--muted"), background: "transparent", overflow: "visible" },
    x: { type: "utc", ticks: Math.max(2, Math.floor(width / (years ? 70 : 110))), tickFormat: short, label: null },
    y: { grid: true, nice: true, tickFormat: yFormat, label: null, ticks: 5 },
    marks: extra,
  });
}

function level(s: Extract<Spec, { kind: "level" }>, width: number) {
  const recent = s.ipi.slice(-37); // three years of published months, then the estimate
  const last = recent[recent.length - 1];
  const est = [{ m: last.m, level: last.v, level_lo: last.v, level_hi: last.v }, ...s.nowcast];
  const end = s.nowcast[s.nowcast.length - 1];
  const fmt = (v: number) => num(s.lang, v, 1);
  const rows = [
    ...recent.map((p) => ({ x: date(p.m), y: p.v, text: `${month(s.lang, p.m)}\n${s.labels.official}${colon(s.lang)}${fmt(p.v)}` })),
    ...s.nowcast.map((p) => ({
      x: date(p.m),
      y: p.level,
      text: `${month(s.lang, p.m)}\n${s.labels.estimate}${colon(s.lang)}${fmt(p.level)} (${pct(s.lang, p.g)})\n${s.labels.band}${colon(s.lang)}${pct(s.lang, p.lo)} … ${pct(s.lang, p.hi)}`,
    })),
  ];
  const ring = css("--page");
  return frame(s.lang, width, 340, (v) => num(s.lang, v, 0), [
    Plot.areaY(est, { x: (d) => date(d.m), y1: "level_lo", y2: "level_hi", fill: css("--band") }),
    Plot.lineY(recent, { x: (d) => date(d.m), y: "v", stroke: css("--series-1"), strokeWidth: 2 }),
    Plot.lineY(est, { x: (d) => date(d.m), y: "level", stroke: css("--series-2"), strokeWidth: 2, strokeDasharray: "5,4" }),
    Plot.dot(s.nowcast, { x: (d) => date(d.m), y: "level", r: 4.5, fill: css("--series-2"), stroke: ring, strokeWidth: 2 }),
    Plot.dot([last], { x: (d) => date(d.m), y: "v", r: 4.5, fill: css("--series-1"), stroke: ring, strokeWidth: 2 }),
    ...(width < 480
      ? []
      : [
          Plot.text([end], { x: (d) => date(d.m), y: "level", text: () => s.labels.estimate, dx: 10, textAnchor: "start", fill: css("--ink"), fontWeight: 600 }),
        ]),
    Plot.ruleX(rows, Plot.pointerX({ x: "x", stroke: css("--baseline") })),
    Plot.tip(rows, Plot.pointerX({ x: "x", y: "y", title: "text", fill: ring, stroke: css("--rule") })),
  ]);
}

function line(s: Extract<Spec, { kind: "line" }>, width: number) {
  const fmt = (v: number) => num(s.lang, v, s.digits);
  const last = s.series[s.series.length - 1];
  const rows = s.series.map((p) => ({ x: date(p.m), y: p.v, text: `${month(s.lang, p.m)}\n${fmt(p.v)}` }));
  return frame(s.lang, width, 220, (v) => num(s.lang, v, 0), [
    ...(s.reference !== undefined ? [Plot.ruleY([s.reference], { stroke: css("--baseline") })] : []),
    Plot.lineY(rows, { x: "x", y: "y", stroke: css("--series-1"), strokeWidth: 2 }),
    Plot.dot([rows[rows.length - 1]], { x: "x", y: "y", r: 4.5, fill: css("--series-1"), stroke: css("--page"), strokeWidth: 2 }),
    ...(width < 480 ? [] : [Plot.text([rows[rows.length - 1]], { x: "x", y: "y", text: () => fmt(last.v), dx: 10, textAnchor: "start", fill: css("--ink"), fontWeight: 600 })]),
    Plot.ruleX(rows, Plot.pointerX({ x: "x", stroke: css("--baseline") })),
    Plot.tip(rows, Plot.pointerX({ x: "x", y: "y", title: "text", fill: css("--page"), stroke: css("--rule") })),
  ], true);
}

function backtest(s: Extract<Spec, { kind: "backtest" }>, width: number) {
  const f = (v: number) => pct(s.lang, v);
  const rows = s.rows.map((r) => ({ x: date(r.m), ...r, text: `${month(s.lang, r.m)}\n${s.labels.actual}${colon(s.lang)}${f(r.actual)}\n${s.labels.estimate}${colon(s.lang)}${f(r.ridge)}` }));
  return frame(s.lang, width, 300, (v) => pct(s.lang, v, 0), [
    Plot.ruleY([0], { stroke: css("--baseline") }),
    Plot.lineY(rows, { x: "x", y: "actual", stroke: css("--series-1"), strokeWidth: 2 }),
    Plot.lineY(rows, { x: "x", y: "ridge", stroke: css("--series-2"), strokeWidth: 2, strokeDasharray: "5,4" }),
    Plot.ruleX(rows, Plot.pointerX({ x: "x", stroke: css("--baseline") })),
    Plot.tip(rows, Plot.pointerX({ x: "x", y: "actual", title: "text", fill: css("--page"), stroke: css("--rule") })),
  ]);
}

// Horizontal bars from zero, largest effect first: blue pushes the estimate up, red pushes it down.
function contrib(s: Extract<Spec, { kind: "contrib" }>, width: number) {
  const rows = [...s.rows].sort((a, b) => Math.abs(b.v) - Math.abs(a.v));
  const fmt = (v: number) => new Intl.NumberFormat(s.lang === "fr" ? "fr-FR" : "en-GB", { minimumFractionDigits: 3, maximumFractionDigits: 3, signDisplay: "exceptZero" }).format(v);
  const left = Math.min(240, Math.round(width * 0.42));
  const extent = Math.max(...rows.map((r) => Math.abs(r.v))) * 1.25;
  const label = (sign: 1 | -1) =>
    Plot.text(rows.filter((r) => Math.sign(r.v) === sign || (sign === 1 && r.v === 0)), {
      x: "v", y: "label", text: (d) => fmt(d.v), dx: 6 * sign, textAnchor: sign === 1 ? "start" : "end", fill: css("--ink"),
    });
  return Plot.plot({
    width,
    height: rows.length * 44 + 30,
    marginLeft: left,
    marginRight: 48,
    style: { fontFamily: css("--font"), fontSize: "13px", color: css("--muted"), background: "transparent", overflow: "visible" },
    x: { domain: [-extent, extent], grid: true, label: null, ticks: 5, tickFormat: (v: number) => num(s.lang, v, 1) },
    y: { domain: rows.map((r) => r.label), label: null, axis: null },
    marks: [
      Plot.axisY({ lineWidth: (left - 12) / 7.5, tickSize: 0, fill: css("--ink-2") }),
      Plot.ruleX([0], { stroke: css("--baseline") }),
      Plot.barX(rows, { x: "v", y: "label", fill: (d) => (d.v >= 0 ? css("--up") : css("--down")), insetTop: 11, insetBottom: 11, rx: 2 }),
      label(1),
      label(-1),
      Plot.tip(rows, Plot.pointerY({ x: "v", y: "label", title: (d) => `${d.label}\n${fmt(d.v)}`, fill: css("--page"), stroke: css("--rule") })),
    ],
  });
}

const draw = { level, line, backtest, contrib } as Record<Spec["kind"], (s: any, w: number) => Element>;

function render(fig: HTMLElement, width: number) {
  tokens = getComputedStyle(document.documentElement);
  const spec = JSON.parse(fig.querySelector("script[type='application/json']")!.textContent!) as Spec;
  const box = fig.querySelector<HTMLElement>(".plot")!;
  const svg = draw[spec.kind](spec, width);
  svg.setAttribute("aria-hidden", "true"); // the figure's label and table carry the content
  box.replaceChildren(svg);
}

const figures = [...document.querySelectorAll<HTMLElement>("figure[data-chart]")];
const lastWidth = new WeakMap<HTMLElement, number>();
const observer = new ResizeObserver((entries) => {
  for (const e of entries) {
    const fig = e.target.closest<HTMLElement>("figure[data-chart]")!;
    const w = Math.round(e.contentRect.width);
    if (lastWidth.get(fig) !== w) {
      lastWidth.set(fig, w);
      render(fig, w);
    }
  }
});
figures.forEach((fig) => observer.observe(fig.querySelector(".plot")!));
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => figures.forEach((f) => render(f, lastWidth.get(f) ?? 0)));
