// Bestellung: prüft die Angaben, holt die interne Bezugsquelle und schickt eine Mail an den Vertrieb.
// Die Bezugsquellen liegen im Cloudflare-KV (Schlüssel "bezugsquellen"), nie im Repo oder im Browser.
import { NACH_SKU } from "./berater.js";

const FELDER = { firma: 120, name: 120, email: 160, telefon: 60, adresse: 400, hinweis: 1000 };

function euro(x) {
  return x.toFixed(2).replace(".", ",") + " €";
}

export function pruefen(d) {
  if (!d || typeof d !== "object") return { fehler: "Ungültige Anfrage." };
  if (d.website) return { fehler: "Ungültige Anfrage." }; // verstecktes Feld, füllen nur Bots aus
  const p = NACH_SKU.get(d.sku);
  if (!p) return { fehler: "Unbekanntes Produkt." };
  let variante = null;
  if (p.varianten.length) {
    variante = p.varianten.find((v) => v.sku === d.variante);
    if (!variante) return { fehler: "Bitte eine Ausführung wählen." };
  }
  const menge = Number(d.menge);
  if (!Number.isInteger(menge) || menge < 1 || menge > 100000) return { fehler: "Bitte eine Menge zwischen 1 und 100000 angeben." };
  const k = {};
  for (const [feld, max] of Object.entries(FELDER)) k[feld] = String(d[feld] ?? "").trim().slice(0, max);
  if (!k.name || !k.adresse) return { fehler: "Bitte Name und Lieferadresse angeben." };
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(k.email)) return { fehler: "Bitte eine gültige E-Mail-Adresse angeben." };
  if (d.zustimmung !== true) return { fehler: "Bitte der Datenverarbeitung zustimmen." };
  const stueck = variante ? variante.preis : p.preis;
  return { produkt: p, variante, menge, kunde: k, stueck, summe: Math.round(stueck * menge * 100) / 100 };
}

export function bestellnummer(jetzt = new Date()) {
  const tag = jetzt.toISOString().slice(0, 10).replaceAll("-", "");
  return `BF-${tag}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`;
}

export function mailText(nr, b, quelle) {
  const { produkt: p, variante: v, menge, kunde: k, stueck, summe } = b;
  const zeilen = [
    `Neue Bestellung über den KI-Berater auf beinundfuß.de`,
    `Bestellnummer: ${nr}`,
    ``,
    `PRODUKT`,
    `${p.name}${p.marke ? ` (${p.marke})` : ""}`,
    `Artikelnummer Shop: ${p.sku}${v ? `, Ausführung: ${v.ausfuehrung} (${v.sku})` : ""}`,
    `Menge: ${menge}`,
    `Stückpreis netto: ${euro(stueck)}${p.preis_ab ? " (ab-Preis, günstigste Ausführung der Serie: Ausführung mit dem Kunden klären)" : ""}`,
    `Summe netto: ${euro(summe)} zzgl. MwSt. und Versand`,
    ``,
    `KUNDE`,
    `Firma: ${k.firma || "-"}`,
    `Name: ${k.name}`,
    `E-Mail: ${k.email}`,
    `Telefon: ${k.telefon || "-"}`,
    `Lieferadresse: ${k.adresse}`,
    `Hinweis: ${k.hinweis || "-"}`,
    ``,
    `INTERN: HIER BESTELLEN (nicht an den Kunden weitergeben)`,
  ];
  if (!quelle) {
    zeilen.push(`Keine Bezugsquelle hinterlegt. Bitte in bezugsquellen.xlsx nachsehen.`);
  } else {
    zeilen.push(`Bezugsquelle: ${quelle.bezugsquelle || "-"}`);
    if (quelle.hersteller) zeilen.push(`Hersteller / Artikel: ${quelle.hersteller}${quelle.artikel ? `, ${quelle.artikel}` : ""}`);
    if (quelle.bestell_url) zeilen.push(`Bestell-Link: ${quelle.bestell_url}`);
    if (quelle.ek_netto != null) {
      zeilen.push(`EK netto laut Recherche: ${euro(quelle.ek_netto)} pro Stück${quelle.preis_bezug ? ` (${quelle.preis_bezug})` : ""}`);
      zeilen.push(`EK gesamt: ${euro(quelle.ek_netto * menge)}, Aufschlag gesamt: ${euro(summe - quelle.ek_netto * menge)}`);
    }
    if (quelle.notiz) zeilen.push(`Notiz: ${quelle.notiz}`);
  }
  zeilen.push(``, `Antworten Sie direkt auf diese Mail, um den Kunden zu erreichen.`);
  return zeilen.join("\n");
}

let bezugCache = null;

export async function bezugsquelle(env, sku) {
  if (!bezugCache && env.BEZUG) bezugCache = (await env.BEZUG.get("bezugsquellen", { type: "json" })) || {};
  return bezugCache?.[sku] ?? null;
}

export async function senden(env, nr, b, text, abruf = fetch) {
  const r = await abruf(env.RESEND_URL || "https://api.resend.com/emails", { // RESEND_URL nur für lokale Tests
    method: "POST",
    headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      from: env.ABSENDER,
      to: [env.BESTELL_EMAIL],
      reply_to: b.kunde.email,
      subject: `Bestellung ${nr}: ${b.menge} × ${b.produkt.name}`,
      text,
    }),
  });
  if (!r.ok) throw new Error(`Mailversand fehlgeschlagen: ${r.status} ${await r.text()}`);
}
