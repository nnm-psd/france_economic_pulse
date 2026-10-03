// RSS feed of archived estimates, newest first (one item per estimate per day), built as a static file.
import data from "./data/site.json";
import { t, month, day, pct, pageUrl, type Lang } from "./i18n";

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

export function feed(lang: Lang, site: URL): Response {
  const home = new URL(pageUrl("overview", lang), site).href;
  const items = data.history.map((h) => {
    const title = t(lang, "rss.item", { month: month(lang, h.m), g: pct(lang, h.g, 2), date: day(lang, h.made) });
    return `<item><title>${esc(title)}</title><link>${home}</link><guid isPermaLink="false">${h.made}-${h.m}</guid><pubDate>${new Date(`${h.made}T06:00:00Z`).toUTCString()}</pubDate></item>`;
  });
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>${esc(t(lang, "rss.title"))}</title><link>${home}</link><description>${esc(t(lang, "overview.description"))}</description><language>${lang}</language>
${items.join("\n")}
</channel></rss>`;
  return new Response(xml, { headers: { "Content-Type": "application/rss+xml; charset=utf-8" } });
}
