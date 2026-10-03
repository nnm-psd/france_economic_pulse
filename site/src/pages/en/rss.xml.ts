import type { APIRoute } from "astro";
import { feed } from "../../rss";

export const GET: APIRoute = ({ site }) => feed("en", site!);
