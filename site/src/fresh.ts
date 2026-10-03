// Which sources are late, judged on the build date against each source's MAX_AGE (D9).
import data from "./data/site.json";

const generated = Date.parse(data.generated);
export const sources = data.sources.map((s) => ({ ...s, late: (generated - Date.parse(s.latest)) / 864e5 > s.max_age_days }));
export const lateSources = sources.filter((s) => s.late);
