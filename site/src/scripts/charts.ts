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
  | { kind: "contrib"; lang: Lang; rows: { label: string; v: number }[] }
  | { kind: "scatter"; lang: Lang; rows: { m: string; actual: number; ridge: number }[]; labels: Record<string, string> }
  | { kind: "rolling"; lang: Lang; rows: { m: string; ridge: number; ar: number }[]; labels: Record<string, string> }
  | { kind: "hist"; lang: Lang; errors: number[]; labels: Record<string, string> }
  | { kind: "weights"; lang: Lang; rows: { m: string; w: number[] }[]; names: string[] }
  | { kind: "evolution"; lang: Lang; days: { made: string; g: number; lo: number; hi: number }[]; actual?: { released: string; v: number }; labels: Record<string, string> };

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
    style: plotStyle(),
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

const plotStyle = () => ({ fontFamily: css("--font"), fontSize: "13px", color: css("--muted"), background: "transparent", overflow: "visible" });

// Estimate vs published figure, one dot per month; the diagonal is a perfect estimate.
function scatter(s: Extract<Spec, { kind: "scatter" }>, width: number) {
  const ext = Math.ceil(Math.max(...s.rows.flatMap((r) => [Math.abs(r.actual), Math.abs(r.ridge)])));
  const f = (v: number) => pct(s.lang, v, 1);
  const size = Math.min(width, 520);
  return Plot.plot({
    width: size,
    height: size,
    marginLeft: 48,
    marginBottom: 44,
    style: plotStyle(),
    x: { domain: [-ext, ext], grid: true, label: s.labels.x, tickFormat: (v: number) => pct(s.lang, v, 0) },
    y: { domain: [-ext, ext], grid: true, label: s.labels.y, tickFormat: (v: number) => pct(s.lang, v, 0) },
    marks: [
      Plot.line([[-ext, -ext], [ext, ext]], { stroke: css("--baseline"), strokeWidth: 1.5 }),
      Plot.dot(s.rows, { x: "actual", y: "ridge", r: 4, fill: css("--series-2"), stroke: css("--page"), strokeWidth: 1.5 }),
      Plot.tip(s.rows, Plot.pointer({
        x: "actual", y: "ridge", fill: css("--page"), stroke: css("--rule"),
        title: (d) => `${month(s.lang, d.m)}\n${s.labels.actual}${colon(s.lang)}${f(d.actual)}\n${s.labels.estimate}${colon(s.lang)}${f(d.ridge)}`,
      })),
    ],
  });
}

// Rolling 24-month RMSE: the estimate (dashed orange, as everywhere) against the naive forecast.
function rolling(s: Extract<Spec, { kind: "rolling" }>, width: number) {
  const rows = s.rows.map((r) => ({ x: date(r.m), ...r }));
  const f = (v: number) => num(s.lang, v, 2);
  // No end labels: the two lines finish close together, so the legend and tooltip carry identity.
  return frame(s.lang, width, 260, (v) => num(s.lang, v, 1), [
    Plot.lineY(rows, { x: "x", y: "ar", stroke: css("--series-3"), strokeWidth: 2 }),
    Plot.lineY(rows, { x: "x", y: "ridge", stroke: css("--series-2"), strokeWidth: 2, strokeDasharray: "5,4" }),
    Plot.ruleX(rows, Plot.pointerX({ x: "x", stroke: css("--baseline") })),
    Plot.tip(rows, Plot.pointerX({
      x: "x", y: "ridge", fill: css("--page"), stroke: css("--rule"),
      title: (d) => `${month(s.lang, d.m)}\n${s.labels.estimate}${colon(s.lang)}${f(d.ridge)}\n${s.labels.ar}${colon(s.lang)}${f(d.ar)}`,
    })),
  ], true);
}

// Distribution of errors in 0.5-point bins.
function hist(s: Extract<Spec, { kind: "hist" }>, width: number) {
  return Plot.plot({
    width,
    height: 220,
    marginLeft: 44,
    style: plotStyle(),
    x: { label: null, tickFormat: (v: number) => num(s.lang, v, 1) },
    y: { grid: true, label: null, ticks: 4 },
    marks: [
      Plot.rectY(s.errors, Plot.binX({ y: "count" }, {
        x: (d) => d, interval: 0.5, fill: css("--series-2"), insetLeft: 1, insetRight: 1, rx: 2,
        tip: { fill: css("--page"), stroke: css("--rule") },
      })),
      Plot.ruleY([0], { stroke: css("--baseline") }),
      Plot.ruleX([0], { stroke: css("--ink-2"), strokeDasharray: "2,3" }),
    ],
  });
}

// Small multiples: one panel per input, shared scales so the weights compare directly.
function weights(s: Extract<Spec, { kind: "weights" }>, width: number) {
  const long = s.rows.flatMap((r) => r.w.map((w, j) => ({ x: date(r.m), w, name: s.names[j] })));
  const ext = Math.max(...long.map((d) => Math.abs(d.w))) * 1.1;
  const tick = Math.round(ext * 6) / 10; // one tick each side, clear of the panel title
  const f = (v: number) => num(s.lang, v, 3);
  return Plot.plot({
    width,
    height: s.names.length * 78 + 30,
    marginLeft: 48,
    marginRight: 16,
    style: plotStyle(),
    x: { type: "utc", ticks: Math.max(2, Math.floor(width / 90)), tickFormat: (d: Date) => String(d.getUTCFullYear()), label: null },
    y: { domain: [-ext, ext], ticks: [-tick, 0, tick], grid: true, label: null, tickFormat: (v: number) => num(s.lang, v, 1) },
    fy: { domain: s.names, axis: null, label: null, padding: 0.35 },
    marks: [
      Plot.ruleY([0], { stroke: css("--baseline") }),
      Plot.lineY(long, { x: "x", y: "w", fy: "name", stroke: css("--ink-2"), strokeWidth: 2 }),
      Plot.text(s.names.map((name) => ({ name })), { fy: "name", text: "name", frameAnchor: "top-left", dy: -12, fill: css("--ink"), fontWeight: 600 }),
      Plot.tip(long, Plot.pointerX({
        x: "x", y: "w", fy: "name", fill: css("--page"), stroke: css("--rule"),
        title: (d) => `${d.name}\n${month(s.lang, iso(d.x))}${colon(s.lang)}${f(d.w)}`,
      })),
    ],
  });
}

// One month's estimate at each daily update (dashed orange, as everywhere), its 80% band, and INSEE's first figure.
function evolution(s: Extract<Spec, { kind: "evolution" }>, width: number) {
  const d = (iso: string) => new Date(`${iso}T00:00:00Z`);
  const rows = s.days.map((r) => ({ x: d(r.made), ...r }));
  const dayFmt = new Intl.DateTimeFormat(s.lang === "fr" ? "fr-FR" : "en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
  const f = (v: number) => pct(s.lang, v, 2);
  const actual = s.actual ? [{ x: d(s.actual.released), v: s.actual.v }] : [];
  return Plot.plot({
    width,
    height: 240,
    marginLeft: 48,
    marginRight: 24,
    style: plotStyle(),
    // Few updates: tick exactly the update days (automatic ticks would repeat a day at sub-day steps).
    x: { type: "utc", label: null, ticks: rows.length <= Math.floor(width / 70) ? rows.map((r) => r.x) : Math.floor(width / 110), tickFormat: (x: Date) => dayFmt.format(x) },
    y: { grid: true, label: null, nice: true, tickFormat: (v: number) => pct(s.lang, v, 1) },
    marks: [
      Plot.ruleY([0], { stroke: css("--baseline") }),
      Plot.areaY(rows, { x: "x", y1: "lo", y2: "hi", fill: css("--band"), curve: "step-after" }),
      Plot.lineY(rows, { x: "x", y: "g", stroke: css("--series-2"), strokeWidth: 2, strokeDasharray: "5,4", curve: "step-after" }),
      Plot.dot(rows.slice(-1), { x: "x", y: "g", r: 4.5, fill: css("--series-2"), stroke: css("--page"), strokeWidth: 2 }),
      Plot.dot(actual, { x: "x", y: "v", r: 5, fill: css("--series-1"), stroke: css("--page"), strokeWidth: 2 }),
      Plot.ruleX(rows, Plot.pointerX({ x: "x", stroke: css("--baseline") })),
      Plot.tip(rows, Plot.pointerX({
        x: "x", y: "g", fill: css("--page"), stroke: css("--rule"),
        title: (r) => `${dayFmt.format(r.x)}\n${s.labels.estimate}${colon(s.lang)}${f(r.g)}\n${s.labels.band}${colon(s.lang)}${f(r.lo)} … ${f(r.hi)}`,
      })),
    ],
  });
}

const draw = { level, line, backtest, contrib, scatter, rolling, hist, weights, evolution } as Record<Spec["kind"], (s: any, w: number) => Element>;

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
// Draw a chart only when it comes near the screen, so charts further down don't block the first paint.
const nearScreen = new IntersectionObserver(
  (entries) => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      nearScreen.unobserve(e.target);
      observer.observe(e.target.querySelector(".plot")!);
    }
  },
  { rootMargin: "300px 0px" },
);
figures.forEach((fig) => nearScreen.observe(fig));
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () =>
  figures.filter((f) => lastWidth.has(f)).forEach((f) => render(f, lastWidth.get(f)!)),
);
