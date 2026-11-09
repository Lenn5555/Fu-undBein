// Sofort bezahlen mit PayPal oder Karte (über PayPal) direkt im Bestellformular (Lenn, 23.10./03.11.2026).
// Der Betrag entsteht nur hier auf dem Server aus Katalog und Versandtabelle, nie im Browser.
// Ablauf: /bezahlen/start legt eine PayPal-Bestellung an, /bezahlen/abschluss prüft sie, zieht das Geld ein
// und gibt die Bestellung frei. Zugangsdaten: Worker-Secrets PAYPAL_CLIENT_ID und PAYPAL_SECRET;
// PAYPAL_SANDBOX = "ja" schaltet auf die PayPal-Testumgebung.
import VERSAND from "./versandkosten.json" with { type: "json" };

export const MWST = 0.19;
// Pauschale je Bestellung: GLS-Preis bis 5 kg für das Lieferland. Größere Mengen klärt der Innendienst.
export const PAUSCHALE_BIS_KG = 5;

const cent = (x) => Math.round(x * 100);
const euro2 = (c) => (c / 100).toFixed(2);

export function aktiv(env) {
  return Boolean(env.PAYPAL_CLIENT_ID && env.PAYPAL_SECRET);
}

function apiBasis(env) {
  return env.PAYPAL_SANDBOX === "ja" ? "https://api-m.sandbox.paypal.com" : "https://api-m.paypal.com";
}

export function versandPauschale(land) {
  if (land === "Deutschland") {
    const t = VERSAND.deutschland;
    return t.preise[t.bis_kg.indexOf(PAUSCHALE_BIS_KG)];
  }
  const t = VERSAND.europa.laender.find((l) => l.land === land);
  return t ? t.preise[VERSAND.europa.bis_kg.indexOf(PAUSCHALE_BIS_KG)] : null;
}

// Endbetrag in Cent: Ware + Versandpauschale, deutsche MwSt. nur bei Lieferung nach Deutschland
// (EU-Ausland mit USt-IdNr.: Reverse Charge; außerhalb der EU: Ausfuhr ohne deutsche MwSt.)
export function betrag(b) {
  const ware = cent(b.summe);
  const versand = cent(versandPauschale(b.kunde.land));
  const mwst = b.kunde.land === "Deutschland" ? Math.round((ware + versand) * MWST) : 0;
  return { ware, versand, mwst, gesamt: ware + versand + mwst };
}

// Sofort bezahlen nur mit festem Stückpreis; bei „ab“-Preisen ohne gewählte Ausführung bestätigt der Innendienst den Preis
export function bezahlbar(b) {
  if (b.produkt.preis_ab && !b.variante) return "Für diese Serie bestätigen wir den Preis Ihrer Ausführung. Bitte „Überweisung (Vorkasse)“ wählen.";
  if (versandPauschale(b.kunde.land) == null) return "Für dieses Lieferland ist Sofortbezahlen nicht möglich.";
  return null;
}

// Fingerabdruck der Bestellung: PayPal speichert ihn, beim Abschluss muss er zu den gesendeten Daten passen
export async function fingerabdruck(b) {
  const k = b.kunde;
  const roh = JSON.stringify([b.produkt.sku, b.variante?.sku || "", b.gewaehlt || {}, b.menge, k.firma, k.name, k.email,
    k.telefon, k.adresse, k.land, k.ust_id, k.hinweis, k.wunsch, k.zahlart, k.rechnung]);
  const h = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(roh));
  return [...new Uint8Array(h)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

async function token(env, abruf) {
  const r = await abruf(`${apiBasis(env)}/v1/oauth2/token`, {
    method: "POST",
    headers: { Authorization: `Basic ${btoa(`${env.PAYPAL_CLIENT_ID}:${env.PAYPAL_SECRET}`)}`, "Content-Type": "application/x-www-form-urlencoded" },
    body: "grant_type=client_credentials",
  });
  if (!r.ok) throw new Error(`PayPal-Anmeldung fehlgeschlagen: ${r.status}`);
  return (await r.json()).access_token;
}

async function paypal(env, abruf, pfad, art, inhalt, extra = {}) {
  const r = await abruf(`${apiBasis(env)}${pfad}`, {
    method: art,
    headers: { Authorization: `Bearer ${await token(env, abruf)}`, "Content-Type": "application/json", ...extra },
    ...(inhalt ? { body: JSON.stringify(inhalt) } : {}),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`PayPal ${art} ${pfad}: ${r.status} ${d.name || ""} ${d.details?.[0]?.issue || ""}`.trim());
  return d;
}

export async function anlegen(env, nr, b, abruf = fetch) {
  const g = betrag(b);
  const was = `${b.menge} × ${b.produkt.name}${b.variante ? `, ${b.variante.ausfuehrung}` : ""}`.slice(0, 127);
  const d = await paypal(env, abruf, "/v2/checkout/orders", "POST", {
    intent: "CAPTURE",
    purchase_units: [{
      amount: { currency_code: "EUR", value: euro2(g.gesamt) },
      description: was,
      custom_id: await fingerabdruck(b),
      invoice_id: nr,
    }],
    application_context: { brand_name: "beinundfuß.de", shipping_preference: "NO_SHIPPING", user_action: "PAY_NOW", locale: "de-DE" },
  });
  return { id: d.id, betrag: g };
}

// Prüft vor dem Einziehen, dass die PayPal-Bestellung genau zu diesen Daten und diesem Betrag gehört
export async function abschliessen(env, id, b, abruf = fetch) {
  if (!/^[A-Z0-9]{8,40}$/.test(String(id))) return { fehler: "Ungültige Zahlung." };
  const o = await paypal(env, abruf, `/v2/checkout/orders/${id}`, "GET");
  const pu = o.purchase_units?.[0] || {};
  const g = betrag(b);
  if (pu.custom_id !== (await fingerabdruck(b)) || pu.amount?.value !== euro2(g.gesamt) || pu.amount?.currency_code !== "EUR")
    return { fehler: "Die Zahlung passt nicht zur Bestellung. Es wurde nichts abgebucht." };
  const c = await paypal(env, abruf, `/v2/checkout/orders/${id}/capture`, "POST", {}, { "PayPal-Request-Id": `bf-${id}` });
  const cap = c.purchase_units?.[0]?.payments?.captures?.[0];
  if (c.status !== "COMPLETED" || !cap || cap.status !== "COMPLETED")
    return { fehler: "Die Zahlung wurde von PayPal nicht abgeschlossen. Bitte erneut versuchen oder Überweisung wählen." };
  return { nr: pu.invoice_id, transaktion: cap.id, betrag: g, wert: cap.amount?.value };
}

export function zahlungsZeilen(z) {
  const e = (c) => euro2(c).replace(".", ",") + " €";
  return [
    `BEZAHLT über PayPal (${z.zahlart}): ${e(z.betrag.gesamt)} brutto, Transaktion ${z.transaktion}.`,
    `  Ware ${e(z.betrag.ware)} + Versandpauschale ${e(z.betrag.versand)}${z.betrag.mwst ? ` + MwSt. ${e(z.betrag.mwst)}` : " (ohne deutsche MwSt.)"}.`,
    `  Ware kann versendet werden. Versand ist mit der Pauschale abgegolten, laut AGB keine Nachberechnung.`,
  ];
}
