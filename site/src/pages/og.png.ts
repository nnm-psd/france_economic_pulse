import type { APIRoute } from "astro";
import { ogImage } from "../og";

export const GET: APIRoute = () => ogImage("fr");
