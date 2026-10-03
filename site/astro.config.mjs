import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";

// GitHub Pages serves this project site under /france_economic_pulse/ (D18).
// Remove `base` when a custom domain is added; every internal URL goes through `url()` in src/i18n.
export default defineConfig({
  site: "https://nnm-psd.github.io",
  base: "/france_economic_pulse",
  trailingSlash: "always",
  build: { inlineStylesheets: "always" }, // one small stylesheet: inline it, nothing blocks first paint
  i18n: {
    locales: ["fr", "en"],
    defaultLocale: "fr",
    routing: { prefixDefaultLocale: false },
  },
  // Pages link their translation with hreflang in <head>; the sitemap just lists every page.
  integrations: [sitemap()],
});
