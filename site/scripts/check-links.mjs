// Fails if any internal link or asset in the built site points to a missing page, file or #anchor.
import { readFileSync, readdirSync, existsSync, statSync } from "node:fs";
import { join } from "node:path";

const DIST = new URL("../dist/", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const BASE = "/france_economic_pulse/";
const pages = (dir) => readdirSync(dir).flatMap((f) => {
  const p = join(dir, f);
  return statSync(p).isDirectory() ? pages(p) : p.endsWith(".html") ? [p] : [];
});
const ids = (file) => new Set([...readFileSync(file, "utf8").matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]));

const errors = [];
for (const page of pages(DIST)) {
  const html = readFileSync(page, "utf8");
  for (const [, ref] of html.matchAll(/\s(?:href|src)="([^"]+)"/g)) {
    if (!ref.startsWith(BASE) && !ref.startsWith("#")) continue; // external links are out of scope
    const [path, anchor] = ref.split("#");
    let file = path ? join(DIST, decodeURI(path.slice(BASE.length)).split("?")[0]) : page;
    if (path && (path.endsWith("/") || !existsSync(file))) file = join(file, "index.html");
    if (!existsSync(file)) errors.push(`${page.slice(DIST.length)}: missing ${ref}`);
    else if (anchor && file.endsWith(".html") && !ids(file).has(anchor)) errors.push(`${page.slice(DIST.length)}: missing anchor ${ref}`);
  }
}
console.log(errors.length ? errors.join("\n") : `links ok (${pages(DIST).length} pages)`);
process.exit(errors.length ? 1 : 0);
