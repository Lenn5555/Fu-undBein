// Cloudflare Worker für beinundfuß.de: POST /beraten (KI-Berater), POST /bestellen (Mail an den Vertrieb),
// POST /zaehlen (anonyme Besucherzählung) und GET /statistik (Bericht, nur mit Schlüssel).
// Geheimnisse (ANTHROPIC_API_KEY, RESEND_API_KEY) liegen als Worker-Secrets bei Cloudflare, nie im Browser.
import Anthropic from "@anthropic-ai/sdk";
import { beraten, neuerClient } from "./berater.js";
import { pruefen, bestellnummer, mailText, bezugsquelle, senden } from "./bestellung.js";
import { meldungPruefen, bestellQuelle, bericht, schluesselPasst } from "./statistik.js";
import { zaehlerVon } from "./zaehler.js";

export { Zaehler } from "./zaehler.js";

const MAX_NACHRICHTEN = 30;
const MAX_ZEICHEN = 1500;

function antwort(daten, status, herkunft) {
  return new Response(JSON.stringify(daten), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      ...(herkunft ? { "Access-Control-Allow-Origin": herkunft, Vary: "Origin" } : {}),
    },
  });
}

function erlaubteHerkunft(env, request) {
  const herkunft = request.headers.get("Origin") || "";
  const liste = (env.HERKUNFT || "").split(",").map((s) => s.trim()).filter(Boolean);
  return liste.includes(herkunft) ? herkunft : null;
}

async function gebremst(env, request, art) {
  if (!env.BREMSE) return false;
  const ip = request.headers.get("CF-Connecting-IP") || "unbekannt";
  const { success } = await env.BREMSE.limit({ key: `${art}:${ip}` });
  return !success;
}

// Zählen darf nie eine Antwort verzögern oder scheitern lassen
function zaehlen(env, ctx, eintraege) {
  const z = zaehlerVon(env);
  if (!z || !eintraege?.length) return;
  const p = z.zaehlen(eintraege).catch((err) => console.error("Zählen:", err));
  if (ctx?.waitUntil) ctx.waitUntil(p);
}

async function statistik(request, env, herkunft) {
  const url = new URL(request.url);
  const schluessel = (request.headers.get("Authorization") || "").replace(/^Bearer\s+/i, "");
  if (!(await schluesselPasst(schluessel, env.STATISTIK_HASH))) return antwort({ fehler: "Falscher Schlüssel." }, 401, herkunft);
  const tage = Math.min(Math.max(parseInt(url.searchParams.get("tage"), 10) || 30, 1), 400);
  const z = zaehlerVon(env);
  if (!z) return antwort({ fehler: "Zählung ist nicht eingerichtet." }, 503, herkunft);
  return antwort(bericht(await z.zeilen(tage), tage), 200, herkunft);
}

export default {
  async fetch(request, env, ctx) {
    const herkunft = erlaubteHerkunft(env, request);
    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: herkunft ? 204 : 403,
        headers: herkunft ? { "Access-Control-Allow-Origin": herkunft, "Access-Control-Allow-Methods": "GET, POST",
                              "Access-Control-Allow-Headers": "Content-Type, Authorization", "Access-Control-Max-Age": "86400", Vary: "Origin" } : {},
      });
    }
    const pfad = new URL(request.url).pathname;
    if (request.method === "GET" && pfad === "/statistik") {
      if (!herkunft) return antwort({ fehler: "Nicht erlaubt." }, 403, null);
      if (await gebremst(env, request, pfad)) return antwort({ fehler: "Zu viele Anfragen. Bitte kurz warten." }, 429, herkunft);
      return statistik(request, env, herkunft);
    }
    if (request.method !== "POST" || !["/beraten", "/bestellen", "/zaehlen"].includes(pfad)) return antwort({ fehler: "Nicht gefunden." }, 404, herkunft);
    if (!herkunft) return antwort({ fehler: "Nicht erlaubt." }, 403, null);
    if (await gebremst(env, request, pfad)) return antwort({ fehler: "Zu viele Anfragen. Bitte kurz warten." }, 429, herkunft);

    let daten;
    try {
      // /zaehlen kommt als text/plain, damit der Browser ohne Vorabfrage senden kann
      daten = JSON.parse(await request.text());
    } catch {
      return antwort({ fehler: "Ungültige Anfrage." }, 400, herkunft);
    }

    if (pfad === "/zaehlen") {
      const eintraege = meldungPruefen(daten);
      if (!eintraege) return antwort({ fehler: "Ungültige Meldung." }, 400, herkunft);
      zaehlen(env, ctx, eintraege);
      return antwort({ ok: true }, 200, herkunft);
    }

    if (pfad === "/beraten") {
      const verlauf = Array.isArray(daten?.verlauf) ? daten.verlauf.slice(-MAX_NACHRICHTEN) : [];
      const sauber = verlauf
        .filter((m) => m && typeof m.text === "string" && m.text.trim())
        .map((m) => ({ rolle: m.rolle === "berater" ? "berater" : "kunde", text: m.text.slice(0, MAX_ZEICHEN) }));
      if (!sauber.length || sauber.at(-1).rolle !== "kunde") return antwort({ fehler: "Bitte eine Frage eingeben." }, 400, herkunft);
      try {
        const { luecke, ...ergebnis } = await beraten(neuerClient(env), sauber, env.MODELL || undefined);
        if (luecke) zaehlen(env, ctx, [{ art: "luecke", wert: luecke, quelle: "berater" }]);
        return antwort(ergebnis, 200, herkunft);
      } catch (err) {
        console.error("Berater:", err instanceof Anthropic.APIError ? `${err.status} ${err.message}` : err);
        const status = err instanceof Anthropic.RateLimitError ? 429 : 502;
        return antwort({ fehler: "Der Berater ist gerade nicht erreichbar. Bitte später noch einmal versuchen." }, status, herkunft);
      }
    }

    const b = pruefen(daten);
    if (b.fehler) return antwort(b, 400, herkunft);
    if (!env.RESEND_API_KEY) return antwort({ fehler: "Online-Bestellung ist noch nicht eingerichtet. Bitte per E-Mail bestellen." }, 503, herkunft);
    const nr = bestellnummer();
    try {
      const quelle = bezugsquelle(b.produkt.sku);
      await senden(env, nr, b, mailText(nr, b, quelle));
    } catch (err) {
      console.error("Bestellung:", err);
      return antwort({ fehler: "Die Bestellung konnte nicht übermittelt werden. Bitte per E-Mail bestellen." }, 502, herkunft);
    }
    zaehlen(env, ctx, [{ art: "ereignis", wert: "bestellung", quelle: bestellQuelle(daten) }]);
    return antwort({ ok: true, bestellnummer: nr }, 200, herkunft);
  },
};
