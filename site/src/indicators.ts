// The four series shown on the site, in display order. Labels live in the i18n files under ind.<key>.
export const INDICATORS = [
  { key: "electricity", digits: 1, source: "rte", reference: 100 },
  { key: "climate", digits: 1, source: "insee", reference: 100 },
  { key: "insolvencies", digits: 0, source: "bodacc" },
  { key: "spread", digits: 0, source: "ecb" },
] as const;
