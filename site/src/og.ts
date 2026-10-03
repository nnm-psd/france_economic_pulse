// Social preview image (1200x630 PNG) built at deploy: the headline and a sparkline of the index plus the estimate.
import sharp from "sharp";
import data from "./data/site.json";
import { t, month, pct, type Lang } from "./i18n";

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;");

function wrap(text: string, max: number): string[] {
  const lines: string[] = [];
  for (const word of text.split(" ")) {
    const last = lines[lines.length - 1];
    if (last && (last + " " + word).length <= max) lines[lines.length - 1] = last + " " + word;
    else lines.push(word);
  }
  return lines;
}

export async function ogImage(lang: Lang): Promise<Response> {
  const latest = data.nowcast[data.nowcast.length - 1];
  const verb = Math.abs(latest.g) < 0.05 ? "overview.flat" : latest.g > 0 ? "overview.up" : "overview.down";
  const headline = t(lang, verb, { g: pct(lang, Math.abs(latest.g), 1, false), month: month(lang, latest.m) });

  // Sparkline: last 36 published months, then the estimate, in a 1080x170 box.
  const pts = [...data.ipi.slice(-36).map((p) => p.v), ...data.nowcast.map((n) => n.level)];
  const lo = Math.min(...pts), hi = Math.max(...pts);
  const xy = pts.map((v, i) => [60 + (i / (pts.length - 1)) * 1080, 590 - ((v - lo) / (hi - lo || 1)) * 150]);
  const split = pts.length - data.nowcast.length - 1;
  const path = (a: number[][]) => a.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join("");

  const font = `font-family="IBM Plex Sans Condensed, IBM Plex Sans, DejaVu Sans, Arial, sans-serif"`;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630">
  <rect width="1200" height="630" fill="#f5f7fa"/>
  <text x="60" y="80" ${font} font-size="30" font-weight="600" fill="#46536b">France Economic Pulse</text>
  ${wrap(headline, 34).map((l, i) => `<text x="60" y="${170 + i * 70}" ${font} font-size="60" font-weight="700" fill="#1d2b44">${esc(l)}</text>`).join("")}
  <path d="${path(xy.slice(0, split + 1))}" fill="none" stroke="#2a78d6" stroke-width="5" stroke-linejoin="round"/>
  <path d="${path(xy.slice(split))}" fill="none" stroke="#eb6834" stroke-width="5" stroke-dasharray="12 9"/>
  <circle cx="${xy[xy.length - 1][0]}" cy="${xy[xy.length - 1][1]}" r="9" fill="#eb6834" stroke="#f5f7fa" stroke-width="4"/>
</svg>`;
  const png = await sharp(Buffer.from(svg)).png().toBuffer();
  return new Response(png, { headers: { "Content-Type": "image/png" } });
}
