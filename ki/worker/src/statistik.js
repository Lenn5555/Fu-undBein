// Anonyme Besucherzählung ohne Cookies: nur Tagessummen je Ereignis und Herkunft, keine IP, keine Texte, keine Kennungen.
// Gespeichert wird im Durable Object Zaehler (zaehler.js); hier steht nur die Prüfung, damit sie ohne Cloudflare testbar ist.

// Was die Seite melden darf. „bestellung“ zählt der Server selbst nach erfolgreichem Versand.
export const EREIGNISSE = ["seitenaufruf", "besuch", "chat_start", "produktkarten", "produktseite", "bestellformular"];
export const QUELLEN = ["werbung", "google", "suchmaschine", "andere_seite", "direkt", "intern"];
export const SEITEN = ["start", "produkt", "kategorie", "uebersicht", "sonstige"];

// Kategorien für „Berater fand nichts“, damit kein Kundentext gespeichert wird
export const LUECKE_BAUFORM = ["Stellfuß", "Stellbein", "Gelenkfuß", "Einschlagfuß", "Schwingungsdämpfer", "Nivellierelement",
  "Gewindestopfen", "Rolle", "anderes"];
export const LUECKE_GRUND = ["Maß oder Gewinde nicht im Sortiment", "Traglast zu hoch", "Material oder Ausführung fehlt",
  "Sonderanfertigung", "anderes Produkt", "Preis", "sonstiges"];

export function heute(jetzt = new Date()) {
  return jetzt.toISOString().slice(0, 10);
}

// Prüft eine Meldung der Seite; gibt die zu zählenden Einträge zurück oder null
export function meldungPruefen(d) {
  if (!d || typeof d !== "object") return null;
  const quelle = QUELLEN.includes(d.quelle) ? d.quelle : "direkt";
  const ereignisse = (Array.isArray(d.ereignisse) ? d.ereignisse : [d.ereignis]).filter((x) => EREIGNISSE.includes(x));
  if (!ereignisse.length) return null;
  const eintraege = [...new Set(ereignisse)].map((e) => ({ art: "ereignis", wert: e, quelle }));
  // Einstiegsseite nur beim Besuch, damit man sieht, ob Leute über Produktseiten von Google kommen
  if (ereignisse.includes("besuch")) eintraege.push({ art: "einstieg", wert: SEITEN.includes(d.seite) ? d.seite : "sonstige", quelle });
  return eintraege;
}

export function lueckePruefen(e) {
  if (!e || !LUECKE_BAUFORM.includes(e.bauform) || !LUECKE_GRUND.includes(e.grund)) return null;
  return `${e.bauform}: ${e.grund}`;
}

// Bestellungen tragen die Herkunft mit, damit man sieht, ob Werbung Käufe bringt
export function bestellQuelle(d) {
  return d && d.herkunft === "werbung" ? "werbung" : "sonstige";
}

// Was eine erfolgreiche Bestellung zählt: nur Summen (Anzahl, Warenwert netto in Cent, Stück je Artikel), nichts zum Kunden
export function bestellEintraege(daten, b) {
  const quelle = bestellQuelle(daten);
  return [
    { art: "ereignis", wert: "bestellung", quelle },
    { art: "umsatz", wert: "netto_cent", quelle, n: Math.round(b.summe * 100) },
    { art: "artikel", wert: `${b.produkt.sku} ${b.produkt.name}`.slice(0, 120), quelle, n: b.menge },
  ];
}

// Zeilen {tag, art, wert, quelle, n} zu einem Bericht für die Statistikseite
export function bericht(zeilen, tage) {
  const summe = {}, werbung = {}, proTag = {}, quellen = {}, einstieg = {}, luecken = {}, artikel = {};
  const umsatz = { netto_cent: 0, werbung_cent: 0, proTag: {} };
  for (const z of zeilen) {
    if (z.art === "ereignis") {
      summe[z.wert] = (summe[z.wert] || 0) + z.n;
      if (z.quelle === "werbung") werbung[z.wert] = (werbung[z.wert] || 0) + z.n;
      const t = (proTag[z.tag] ||= {});
      t[z.wert] = (t[z.wert] || 0) + z.n;
      if (z.wert === "besuch") quellen[z.quelle] = (quellen[z.quelle] || 0) + z.n;
    } else if (z.art === "einstieg") einstieg[z.wert] = (einstieg[z.wert] || 0) + z.n;
    else if (z.art === "luecke") luecken[z.wert] = (luecken[z.wert] || 0) + z.n;
    else if (z.art === "umsatz") {
      umsatz.netto_cent += z.n;
      if (z.quelle === "werbung") umsatz.werbung_cent += z.n;
      umsatz.proTag[z.tag] = (umsatz.proTag[z.tag] || 0) + z.n;
    } else if (z.art === "artikel") artikel[z.wert] = (artikel[z.wert] || 0) + z.n;
  }
  return { tage, summe, werbung, proTag, quellen, einstieg, luecken, umsatz, artikel };
}

export async function schluesselPasst(schluessel, hash) {
  if (!schluessel || !hash) return false;
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(schluessel));
  const hex = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
  return hex === hash.toLowerCase();
}
