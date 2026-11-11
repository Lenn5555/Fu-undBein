// Bestellung: prüft die Angaben, holt die interne Bezugsquelle und schickt eine Mail an den Vertrieb.
// Die Bezugsquellen (Händler, EK) stecken in src/bezugsquellen.json. Die Datei steht NICHT im Repo:
// Beim Veröffentlichen entsteht sie aus dem GitHub-Secret BEZUGSQUELLEN und landet nur im Worker bei Cloudflare.
import { NACH_SKU } from "./berater.js";
import BEZUGSQUELLEN from "./bezugsquellen.json" with { type: "json" };
import VERSAND from "./versandkosten.json" with { type: "json" };
import { zahlungsZeilen, betrag } from "./bezahlen.js";

// Lieferländer aus der Versandtabelle; EU-Ausland nur mit USt-IdNr. (Lieferung ohne deutsche MwSt.)
const LAENDER = new Map([["Deutschland", { eu: true }], ...VERSAND.europa.laender.map((l) => [l.land, l])]);

const ZAHLARTEN = ["Überweisung (Vorkasse)", "Kreditkarte", "PayPal"];

const FELDER = { firma: 120, name: 120, email: 160, telefon: 60, adresse: 400, strasse: 120, zusatz: 120, plz: 10, ort: 80,
  hinweis: 1000, wunsch: 200, land: 60, ust_id: 20, zahlart: 40 };
// Abweichende Rechnungsadresse (nur wenn „gleich Lieferadresse“ abgewählt ist)
const R_FELDER = { firma: 120, name: 120, strasse: 120, zusatz: 120, plz: 10, ort: 80, land: 60 };

function plzOk(plz, land) {
  return land === "Deutschland" ? /^\d{5}$/.test(plz) : /^[0-9A-Za-z][0-9A-Za-z -]{1,9}$/.test(plz);
}
function zeilenAdresse(a) {
  return [a.firma, a.name, a.strasse, a.zusatz, `${a.plz} ${a.ort}`.trim(), a.land].filter(Boolean);
}

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
  if (!k.name) return { fehler: "Bitte einen Namen angeben." };
  // Lieferadresse in einzelnen Feldern; „adresse“ (ein Textfeld) nur noch für alte Seitenstände
  if (k.strasse || k.plz || k.ort) {
    if (!k.strasse || !k.plz || !k.ort) return { fehler: "Bitte Straße, PLZ und Ort der Lieferadresse angeben." };
  } else if (!k.adresse) return { fehler: "Bitte die Lieferadresse angeben." };
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(k.email)) return { fehler: "Bitte eine gültige E-Mail-Adresse angeben." };
  if (!k.land) k.land = "Deutschland";
  const land = LAENDER.get(k.land);
  if (!land) return { fehler: "Bitte ein Lieferland aus der Liste wählen." };
  if (k.plz && !plzOk(k.plz, k.land)) return { fehler: "Bitte eine gültige Postleitzahl der Lieferadresse angeben." };
  if (k.strasse) k.adresse = [k.strasse, k.zusatz, `${k.plz} ${k.ort}`].filter(Boolean).join(", ");
  // Rechnungsadresse: gleich Lieferadresse, außer der Kunde hat eine andere angegeben
  k.rechnung = null;
  if (d.rechnung_gleich === false) {
    const r = {};
    const roh = d.rechnung && typeof d.rechnung === "object" ? d.rechnung : {};
    for (const [feld, max] of Object.entries(R_FELDER)) r[feld] = String(roh[feld] ?? "").trim().slice(0, max);
    if (!r.firma && !r.name) return { fehler: "Bitte Firma oder Name für die Rechnungsadresse angeben." };
    if (!r.strasse || !r.plz || !r.ort || !r.land) return { fehler: "Bitte Straße, PLZ, Ort und Land der Rechnungsadresse angeben." };
    if (!plzOk(r.plz, r.land)) return { fehler: "Bitte eine gültige Postleitzahl der Rechnungsadresse angeben." };
    k.rechnung = r;
  }
  k.ust_id = k.ust_id.replace(/[\s.-]/g, "").toUpperCase();
  if (k.land !== "Deutschland" && land.eu && !/^[A-Z]{2}[0-9A-Z+*]{2,12}$/.test(k.ust_id))
    return { fehler: "Für Lieferungen ins EU-Ausland brauchen wir Ihre USt-IdNr. (z. B. IT12345678901)." };
  if (!k.zahlart) k.zahlart = ZAHLARTEN[0];
  if (!ZAHLARTEN.includes(k.zahlart)) return { fehler: "Bitte eine Zahlungsart wählen." };
  if (d.zustimmung !== true) return { fehler: "Bitte der Datenverarbeitung zustimmen." };
  const stueck = variante ? variante.preis : p.preis;
  const summe = Math.round(stueck * menge * 100) / 100;
  if (p.mindestwert && summe < p.mindestwert)
    return { fehler: `Für diesen Artikel gilt ein Mindestbestellwert von ${euro(p.mindestwert)} netto, also ab ${Math.ceil(p.mindestwert / stueck)} Stück.` };
  return { produkt: p, variante, gewaehlt, menge, kunde: k, stueck, summe, zuschlag: mindermenge(p, summe) };
}

// Mindermengenzuschlag für Händlerware unter dem Mindestwarenwert (Lenn, 10.11.2026)
export function mindermenge(p, summe) {
  const s = p.mindermenge && VERSAND.mindermenge ? VERSAND.mindermenge.stufen.find((x) => summe < x.unter) : null;
  return s ? s.zuschlag : 0;
}

export function bestellnummer(jetzt = new Date()) {
  const tag = jetzt.toISOString().slice(0, 10).replaceAll("-", "");
  return `BF-${tag}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`;
}

// zahlung: nur bei Sofortbezahlung über PayPal (siehe bezahlen.js)
export function mailText(nr, b, quelle, zahlung = null) {
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
    ...(b.zuschlag ? [`Mindermengenzuschlag: ${euro(b.zuschlag)} netto (Warenwert unter ${euro(VERSAND.mindermenge.stufen.find((x) => b.summe < x.unter).unter)})`] : []),
    `Versand: ${k.land === "Deutschland" ? `pauschal ${euro(VERSAND.deutschland.pauschal)} netto` : "nach GLS-Tarif je Paketgewicht (siehe Versandkosten)"}`,
    ``,
    `KUNDE`,
    `Firma: ${k.firma || "-"}`,
    `Name: ${k.name}`,
    `E-Mail: ${k.email}`,
    `Telefon: ${k.telefon || "-"}`,
    `USt-IdNr.: ${k.ust_id || "-"}`,
    `Hinweis: ${k.hinweis || "-"}`,
    ``,
    `LIEFERADRESSE`,
    ...(k.strasse ? zeilenAdresse({ firma: k.firma, name: k.name, strasse: k.strasse, zusatz: k.zusatz, plz: k.plz, ort: k.ort, land: k.land })
      : [k.adresse, k.land]),
    ``,
    `RECHNUNGSADRESSE`,
    ...(k.rechnung ? zeilenAdresse(k.rechnung) : [`gleich Lieferadresse`]),
    ``,
    ...(zahlung ? zahlungsZeilen(zahlung) : (k.zahlart.startsWith("Überweisung")
      ? [`ZAHLUNG: Vorkasse per Überweisung. Der Kunde hat nach der Bestellung unsere Bankverbindung mit Verwendungszweck ${nr} gesehen` +
         (k.land === "Deutschland" ? `, Betrag ${euro(betrag(b).gesamt / 100)} brutto.` : `, Betrag folgt mit der Auftragsbestätigung (Ausland).`) +
         ` Erst nach Zahlungseingang versenden.`]
      : [`ZAHLUNG: Vorkasse per ${k.zahlart}. Zahlungslink mit der Auftragsbestätigung schicken, erst nach Zahlungseingang versenden.`])),
    ``,
    ...(k.land === "Deutschland" ? [] : [
      `AUSLANDSBESTELLUNG: ${LAENDER.get(k.land)?.eu ? "EU, ohne deutsche MwSt. (Reverse Charge). USt-IdNr. vor der Auftragsbestätigung im EU-System VIES prüfen, Lieferung in die Zusammenfassende Meldung." : "Nicht-EU: Zoll und Ausfuhrpapiere klären, Versand mit dem Kunden absprechen."}`,
      ``,
    ]),
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

// Bei Ausführungen mit eigenem Händlerartikel (feste Preise je Ausführung) gilt deren Artikel und EK
export function bezugsquelle(sku, varianteSku = null) {
  const q = BEZUGSQUELLEN[sku];
  if (!q) return null;
  const { varianten, ...rest } = q;
  const v = varianteSku && varianten ? varianten[varianteSku] : null;
  return v ? { ...rest, ...v } : rest;
}

export async function senden(env, nr, b, text, abruf = fetch, bezahlt = false) {
  const r = await abruf(env.RESEND_URL || "https://api.resend.com/emails", { // RESEND_URL nur für lokale Tests
    method: "POST",
    headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      from: env.ABSENDER,
      to: [env.BESTELL_EMAIL],
      reply_to: b.kunde.email,
      // Nur einfache Zeichen im Betreff: Outlook am Computer meldet sonst "Dateiname ungültig" und zeigt die Mail leer
      subject: `Bestellung ${nr}${bezahlt ? " (bezahlt)" : ""}`,
      text,
      html: mailHtml(text),
    }),
  });
  if (!r.ok) throw new Error(`Mailversand fehlgeschlagen: ${r.status} ${await r.text()}`);
}

// Eingangsbestätigung an den Kunden (Lenn, 11.11.2026). Ohne Bezugsquelle, Hersteller und Artikelnummern.
// Verbindlich wird die Bestellung erst mit der Auftragsbestätigung des Innendienstes.
// Absender: "Bein und Fuss <bestellung@ts-systec.de>", geht nur, wenn ts-systec.de bei Resend bestätigt ist.
export function kundenText(nr, b, env, zahlung = null) {
  const { produkt: p, variante: v, gewaehlt = {}, menge, kunde: k, stueck, summe } = b;
  const wahl = v ? v.ausfuehrung : Object.entries(gewaehlt).map(([m, w]) => `${m} ${w}`).join(", ");
  const de = k.land === "Deutschland";
  const s = betrag(b);
  const iban = env.BANK_IBAN, inhaber = env.BANK_INHABER;
  const zeilen = [
    `Guten Tag ${k.name},`,
    ``,
    `vielen Dank für Ihre Bestellung. Sie ist bei uns eingegangen.`,
    ``,
    `Bestellnummer: ${nr}`,
    ``,
    `IHRE BESTELLUNG`,
    p.name,
    ...(wahl ? [`Ausführung: ${wahl}`] : []),
    ...(k.wunsch ? [`Ihr Wunsch zur Ausführung: ${k.wunsch}`] : []),
    `Menge: ${menge}`,
    `Stückpreis netto: ${euro(stueck)}`,
    `Warenwert netto: ${euro(summe)}`,
    ...(b.zuschlag ? [`Mindermengenzuschlag netto: ${euro(b.zuschlag)}`] : []),
    ...(de
      ? [`Versand netto: ${euro(s.versand / 100)}`, `MwSt. 19 %: ${euro(s.mwst / 100)}`, `Gesamtbetrag: ${euro(s.gesamt / 100)}`]
      : [`Versand: nach Paketgewicht, den Betrag nennen wir Ihnen mit der Auftragsbestätigung.`]),
    ``,
    `LIEFERADRESSE`,
    ...(k.strasse ? zeilenAdresse({ firma: k.firma, name: k.name, strasse: k.strasse, zusatz: k.zusatz, plz: k.plz, ort: k.ort, land: k.land })
      : [k.adresse, k.land]),
    ``,
    `RECHNUNGSADRESSE`,
    ...(k.rechnung ? zeilenAdresse(k.rechnung) : [`gleich Lieferadresse`]),
    ``,
    `ZAHLUNG`,
  ];
  if (zahlung) {
    zeilen.push(`Bezahlt per ${k.zahlart}: ${euro(s.gesamt / 100)}. Vielen Dank.`);
  } else if (k.zahlart.startsWith("Überweisung") && iban) {
    zeilen.push(
      `Bitte überweisen Sie ${de ? euro(s.gesamt / 100) : "den Betrag aus der Auftragsbestätigung"} auf dieses Konto:`,
      `Empfänger: ${inhaber}`,
      `IBAN: ${iban}`,
      `Verwendungszweck: ${nr}`,
      `Bitte geben Sie die Bestellnummer als Verwendungszweck an, damit wir Ihre Zahlung zuordnen können.`,
    );
  } else {
    zeilen.push(`Vorkasse per ${k.zahlart}. Den Zahlungslink schicken wir Ihnen mit der Auftragsbestätigung.`);
  }
  zeilen.push(
    ``,
    `Dies ist eine automatische Eingangsbestätigung. Verbindlich wird Ihre Bestellung mit unserer Auftragsbestätigung, die wir Ihnen gesondert schicken.` +
      (zahlung ? ` Wir versenden so schnell wie möglich.` : ` Wir versenden nach Zahlungseingang.`),
    ``,
    `Fragen? Antworten Sie einfach auf diese Mail.`,
    ``,
    `Mit freundlichen Grüßen`,
    `Bein und Fuss`,
    `T&S Systemtechnik GmbH, Pfungstadt`,
    `beinundfuß.de`,
  );
  return zeilen.join("\n");
}

// Schickt die Eingangsbestätigung, nur wenn KUNDENMAIL = "an". Fehler stoppen die Bestellung nicht.
export async function kundeBenachrichtigen(env, nr, b, zahlung = null, abruf = fetch) {
  if (env.KUNDENMAIL !== "an" || !env.KUNDEN_ABSENDER) return false;
  const text = kundenText(nr, b, env, zahlung);
  try {
    const r = await abruf(env.RESEND_URL || "https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        from: env.KUNDEN_ABSENDER,
        to: [b.kunde.email],
        reply_to: env.BESTELL_EMAIL,
        // Nur einfache Zeichen im Betreff (Outlook, siehe senden)
        subject: `Ihre Bestellung ${nr} bei Bein und Fuss`,
        text,
        html: mailHtml(text),
      }),
    });
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return true;
  } catch (err) {
    console.error(`Eingangsbestätigung ${nr} an den Kunden fehlgeschlagen:`, err.message);
    return false;
  }
}
