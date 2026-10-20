// Bestellung: prüft die Angaben, holt die interne Bezugsquelle und schickt eine Mail an den Vertrieb.
// Die Bezugsquellen (Händler, EK) stecken in src/bezugsquellen.json. Die Datei steht NICHT im Repo:
// Beim Veröffentlichen entsteht sie aus dem GitHub-Secret BEZUGSQUELLEN und landet nur im Worker bei Cloudflare.
import { NACH_SKU } from "./berater.js";
import BEZUGSQUELLEN from "./bezugsquellen.json" with { type: "json" };

const FELDER = { firma: 120, name: 120, email: 160, telefon: 60, adresse: 400, hinweis: 1000, wunsch: 200 };

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
  // Wählbare Merkmale ohne eigenen Preis (z. B. Gewinde): nur Werte aus dem Katalog
  const gewaehlt = {};
  for (const [merkmal, werte] of Object.entries(p.optionen || {})) {
    const wahl = d.optionen && typeof d.optionen === "object" ? d.optionen[merkmal] : undefined;
    if (!werte.includes(wahl)) return { fehler: `Bitte ${merkmal} wählen.` };
    gewaehlt[merkmal] = wahl;
  }
  const menge = Number(d.menge);
  if (!Number.isInteger(menge) || menge < 1 || menge > 100000) return { fehler: "Bitte eine Menge zwischen 1 und 100000 angeben." };
  const k = {};
  for (const [feld, max] of Object.entries(FELDER)) k[feld] = String(d[feld] ?? "").trim().slice(0, max);
  if (!k.name || !k.adresse) return { fehler: "Bitte Name und Lieferadresse angeben." };
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(k.email)) return { fehler: "Bitte eine gültige E-Mail-Adresse angeben." };
  if (d.zustimmung !== true) return { fehler: "Bitte der Datenverarbeitung zustimmen." };
  const stueck = variante ? variante.preis : p.preis;
  return { produkt: p, variante, gewaehlt, menge, kunde: k, stueck, summe: Math.round(stueck * menge * 100) / 100 };
}

export function bestellnummer(jetzt = new Date()) {
  const tag = jetzt.toISOString().slice(0, 10).replaceAll("-", "");
  return `BF-${tag}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`;
}

export function mailText(nr, b, quelle) {
  const { produkt: p, variante: v, gewaehlt = {}, menge, kunde: k, stueck, summe } = b;
  const wahl = Object.entries(gewaehlt).map(([m, w]) => `${m} ${w}`).join(", ");
  // Eindeutige Kennung der bestellten Ausführung, auch für die Preisüberwachung
  const kennung = v ? v.sku : [p.sku, ...Object.entries(gewaehlt).map(([m, w]) => `${m}=${w}`)].join("|");
  const zeilen = [
    `Neue Bestellung über den KI-Berater auf beinundfuß.de`,
    `Bestellnummer: ${nr}`,
    ``,
    `PRODUKT`,
    `${p.name}${p.marke ? ` (${p.marke})` : ""}`,
    `Artikelnummer Shop: ${p.sku}`,
    `BESTELLTE AUSFÜHRUNG: ${v ? `${v.ausfuehrung} (Artikelnummer ${v.sku})` : wahl || "Serie wie angezeigt, keine Auswahl nötig"}`,
    ...(k.wunsch ? [`Wunsch des Kunden zur Ausführung: ${k.wunsch}`] : []),
    `Kennung: ${kennung}`,
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

// Manche Mail-Apps zeigen reine Textmails leer an, deshalb geht der gleiche Text auch als HTML mit.
// Einfaches HTML mit <br> statt CSS-Umbrüchen, weil Outlook am Computer kaum CSS kennt.
export function mailHtml(text) {
  const sicher = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1">$1</a>')
    .replace(/\n/g, "<br>\n");
  return `<!DOCTYPE html><html><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8"></head>` +
    `<body style="background:#ffffff;color:#000000"><p style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:20px;color:#000000">${sicher}</p></body></html>`;
}

export function bezugsquelle(sku) {
  return BEZUGSQUELLEN[sku] ?? null;
}

export async function senden(env, nr, b, text, abruf = fetch) {
  const r = await abruf(env.RESEND_URL || "https://api.resend.com/emails", { // RESEND_URL nur für lokale Tests
    method: "POST",
    headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      from: env.ABSENDER,
      to: [env.BESTELL_EMAIL],
      reply_to: b.kunde.email,
      // Nur einfache Zeichen im Betreff: Outlook am Computer meldet sonst "Dateiname ungültig" und zeigt die Mail leer
      subject: `Bestellung ${nr}`,
      text,
      html: mailHtml(text),
    }),
  });
  if (!r.ok) throw new Error(`Mailversand fehlgeschlagen: ${r.status} ${await r.text()}`);
}
