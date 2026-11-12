// Cloudflare Worker für beinundfuß.de: POST /beraten (KI-Berater), POST /bestellen (Mail an den Vertrieb),
// POST /zaehlen (anonyme Besucherzählung), GET /statistik (Bericht, nur mit Schlüssel) und
// GET /bezahlen, POST /bezahlen/start und /bezahlen/abschluss (Sofortbezahlen über PayPal, siehe bezahlen.js).
// Der Abendbericht der Sekretärin liest /statistik ohne Browser mit einem eigenen Schlüssel (BERICHT_HASH).
// Geheimnisse (ANTHROPIC_API_KEY, RESEND_API_KEY) liegen als Worker-Secrets bei Cloudflare, nie im Browser.
import Anthropic from "@anthropic-ai/sdk";
import { beraten, neuerClient } from "./berater.js";
import { pruefen, bestellnummer, mailText, bezugsquelle, senden, kundeBenachrichtigen } from "./bestellung.js";
import { meldungPruefen, bestellEintraege, bericht, schluesselPasst } from "./statistik.js";
import { zaehlerVon } from "./zaehler.js";
import { aktiv, bezahlbar, anlegen, abschliessen, betrag } from "./bezahlen.js";

const SOFORT = ["PayPal", "Kreditkarte"];

export { Zaehler } from "./zaehler.js";
export { Lager } from "./lager.js";
import { lagerVon } from "./lager.js";
import { lagerArtikel, lagerFehler, TS_ARTIKEL } from "./lagerkern.js";
import { lagerEingang } from "./eingang.js";

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
  // Aus dem Browser nur Lenns Schlüssel; ohne erlaubte Herkunft nur der Berichtsschlüssel
  const hash = herkunft ? env.STATISTIK_HASH : env.BERICHT_HASH;
  const passt = (await schluesselPasst(schluessel, hash)) || (herkunft && (await schluesselPasst(schluessel, env.BERICHT_HASH)));
  if (!passt) return antwort({ fehler: "Falscher Schlüssel." }, 401, herkunft);
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
      if (await gebremst(env, request, pfad)) return antwort({ fehler: "Zu viele Anfragen. Bitte kurz warten." }, 429, herkunft);
      return statistik(request, env, herkunft);
    }
    // Webhook von Resend: Lagerdatei per Mail (siehe eingang.js); ohne Herkunftsprüfung, dafür mit Signatur
    if (request.method === "POST" && pfad === "/lager/eingang") {
      try {
        const r = await lagerEingang(request, env, lagerVon(env));
        return new Response(r.text, { status: r.status });
      } catch (err) {
        console.error("Lager-Eingang:", err.message);
        return new Response("Fehler", { status: 500 });
      }
    }
    // Lagerbestand der T&S-Artikel für die Anzeige auf der Seite (nur Artikelnummer und Menge)
    if (request.method === "GET" && pfad === "/bestand") {
      const lager = lagerVon(env);
      const d = lager ? await lager.alle() : { stand: null, artikel: {} };
      const artikel = {};
      for (const [a, n] of Object.entries(d.artikel)) if (TS_ARTIKEL.has(a)) artikel[a] = n;
      return antwort({ stand: d.stand, artikel }, 200, herkunft);
    }
    // Öffentliche Client-ID für die PayPal-Knöpfe; ohne Zugangsdaten bleibt es bei Vorkasse mit Zahlungslink
    if (request.method === "GET" && pfad === "/bezahlen") {
      return antwort(aktiv(env) ? { aktiv: true, client_id: env.PAYPAL_CLIENT_ID, sandbox: env.PAYPAL_SANDBOX === "ja" } : { aktiv: false }, 200, herkunft);
    }
    if (request.method !== "POST" || !["/beraten", "/bestellen", "/zaehlen", "/bezahlen/start", "/bezahlen/abschluss"].includes(pfad)) return antwort({ fehler: "Nicht gefunden." }, 404, herkunft);
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
    if (pfad.startsWith("/bezahlen/")) return bezahlen(pfad, daten, b, env, ctx, herkunft);
    if (!env.RESEND_API_KEY) return antwort({ fehler: "Online-Bestellung ist noch nicht eingerichtet. Bitte per E-Mail bestellen." }, 503, herkunft);
    const nr = bestellnummer();
    // Lager: Menge reservieren, bevor die Bestellung rausgeht (nur T&S-Artikel mit hinterlegtem Bestand)
    const lager = lagerVon(env), artikel = lagerArtikel(b);
    let abgezogen = false;
    if (lager && artikel) {
      const l = await lager.abziehen(artikel, b.menge);
      if (!l.ok) return antwort({ fehler: lagerFehler(l.rest, env.BESTELL_EMAIL), bestand: l.rest }, 409, herkunft);
      abgezogen = l.rest !== null;
    }
    try {
      const quelle = bezugsquelle(b.produkt.sku, b.variante?.sku);
      await senden(env, nr, b, mailText(nr, b, quelle));
      await kundeBenachrichtigen(env, nr, b);
    } catch (err) {
      if (abgezogen) await lager.zurueck(artikel, b.menge);
      console.error("Bestellung:", err);
      return antwort({ fehler: "Die Bestellung konnte nicht übermittelt werden. Bitte per E-Mail bestellen." }, 502, herkunft);
    }
    zaehlen(env, ctx, bestellEintraege(daten, b));
    // Für die Überweisung: Endbetrag nur bei Lieferung nach Deutschland (Ausland: Betrag mit der Auftragsbestätigung)
    return antwort({ ok: true, bestellnummer: nr, ...(b.kunde.land === "Deutschland" ? { gesamt: betrag(b).gesamt } : {}) }, 200, herkunft);
  },
};

async function bezahlen(pfad, daten, b, env, ctx, herkunft) {
  if (!aktiv(env) || !env.RESEND_API_KEY) return antwort({ fehler: "Sofortbezahlen ist noch nicht eingerichtet. Bitte „Überweisung (Vorkasse)“ wählen." }, 503, herkunft);
  if (!SOFORT.includes(b.kunde.zahlart)) return antwort({ fehler: "Bitte PayPal oder Kreditkarte wählen." }, 400, herkunft);
  const nein = bezahlbar(b);
  if (nein) return antwort({ fehler: nein }, 400, herkunft);
  const lager = lagerVon(env), artikel = lagerArtikel(b);
  if (pfad === "/bezahlen/start") {
    if (lager && artikel) {
      const l = await lager.pruefen(artikel, b.menge);
      if (!l.ok) return antwort({ fehler: lagerFehler(l.rest, env.BESTELL_EMAIL), bestand: l.rest }, 409, herkunft);
    }
    try {
      const o = await anlegen(env, bestellnummer(), b);
      return antwort({ ok: true, id: o.id, gesamt: o.betrag.gesamt }, 200, herkunft);
    } catch (err) {
      console.error("PayPal anlegen:", err.message);
      return antwort({ fehler: "PayPal ist gerade nicht erreichbar. Bitte später erneut versuchen oder „Überweisung (Vorkasse)“ wählen." }, 502, herkunft);
    }
  }
  let z;
  try {
    z = await abschliessen(env, daten.paypal_id, b);
  } catch (err) {
    console.error("PayPal abschließen:", err.message);
    return antwort({ fehler: "Die Zahlung konnte nicht abgeschlossen werden. Es wurde nichts abgebucht, bitte erneut versuchen." }, 502, herkunft);
  }
  if (z.fehler) return antwort(z, 400, herkunft);
  // Bezahlt: Bestand immer abziehen (höchstens bis 0)
  if (lager && artikel) await lager.erzwingen(artikel, b.menge);
  // Geld ist eingezogen: die Bestellung gilt auch dann, wenn die Mail scheitert (dann steht sie im Protokoll und bei PayPal)
  try {
    await senden(env, z.nr, b, mailText(z.nr, b, bezugsquelle(b.produkt.sku, b.variante?.sku), { ...z, zahlart: b.kunde.zahlart }), fetch, true);
    await kundeBenachrichtigen(env, z.nr, b, z);
  } catch (err) {
    console.error(`Mail zur bezahlten Bestellung ${z.nr} (PayPal ${z.transaktion}) fehlgeschlagen:`, err.message);
  }
  zaehlen(env, ctx, bestellEintraege(daten, b));
  return antwort({ ok: true, bestellnummer: z.nr, gesamt: betrag(b).gesamt }, 200, herkunft);
}
