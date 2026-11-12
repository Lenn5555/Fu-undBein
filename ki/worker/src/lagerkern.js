// Lagerbestand der T&S-Artikel (Lenn, 12.11.2026). Jeden Morgen kommt eine Excel-Datei aus dem Innendienst,
// die den Bestand komplett ersetzt; jede Bestellung zieht ihre Menge ab. Schlüssel ist die T&S-Artikelnummer
// (bei uns die SKU der Ausführung). Artikel ohne Eintrag gelten als unbegrenzt, damit ein fehlender Abgleich
// den Verkauf nicht stoppt. Die Logik steht hier ohne Cloudflare-Abhängigkeit, damit sie testbar ist.
import { NACH_SKU } from "./berater.js";

// sql: exec(abfrage, ...werte) mit .toArray(); transaktion: führt eine Funktion atomar aus
export class LagerKern {
  constructor(sql, transaktion = (f) => f()) {
    this.sql = sql; this.transaktion = transaktion;
    sql.exec("CREATE TABLE IF NOT EXISTS bestand (artikel TEXT PRIMARY KEY, menge INTEGER NOT NULL)");
    sql.exec("CREATE TABLE IF NOT EXISTS info (schluessel TEXT PRIMARY KEY, wert TEXT NOT NULL)");
  }

  // Ersetzt den ganzen Bestand (Morgendatei). liste: [{ artikel, menge }]
  setzen(liste, stand, quelle) {
    this.transaktion(() => {
      this.sql.exec("DELETE FROM bestand");
      for (const z of liste) this.sql.exec("INSERT OR REPLACE INTO bestand (artikel, menge) VALUES (?, ?)", z.artikel, z.menge);
      this.sql.exec("INSERT OR REPLACE INTO info (schluessel, wert) VALUES ('stand', ?), ('quelle', ?)", stand, quelle || "");
    });
    return liste.length;
  }

  alle() {
    const artikel = {};
    for (const z of this.sql.exec("SELECT artikel, menge FROM bestand").toArray()) artikel[z.artikel] = z.menge;
    const info = {};
    for (const z of this.sql.exec("SELECT schluessel, wert FROM info").toArray()) info[z.schluessel] = z.wert;
    return { stand: info.stand || null, artikel };
  }

  pruefen(artikel, menge) {
    const z = this.sql.exec("SELECT menge FROM bestand WHERE artikel = ?", artikel).toArray()[0];
    return z ? { ok: menge <= z.menge, rest: z.menge } : { ok: true, rest: null };
  }

  // Zieht nur ab, wenn genug da ist. Ergebnis: { ok, rest } (rest = null: kein Bestand hinterlegt)
  abziehen(artikel, menge) {
    const p = this.pruefen(artikel, menge);
    if (!p.ok || p.rest === null) return p;
    this.sql.exec("UPDATE bestand SET menge = menge - ? WHERE artikel = ?", menge, artikel);
    return { ok: true, rest: p.rest - menge };
  }

  // Bereits bezahlte Bestellung: immer abziehen, nicht unter 0
  erzwingen(artikel, menge) {
    this.sql.exec("UPDATE bestand SET menge = MAX(0, menge - ?) WHERE artikel = ?", menge, artikel);
  }

  zurueck(artikel, menge) {
    this.sql.exec("UPDATE bestand SET menge = menge + ? WHERE artikel = ?", menge, artikel);
  }
}

// Nur T&S-Ware (ohne Mindermengenzuschlag) hat einen Lagerbestand; Schlüssel = Artikelnummer der Ausführung
export function lagerArtikel(b) {
  if (b.produkt.mindermenge) return null;
  return b.variante ? b.variante.sku : b.produkt.sku;
}

export const TS_ARTIKEL = new Set([...NACH_SKU.values()].filter((p) => !p.mindermenge)
  .flatMap((p) => (p.varianten.length ? p.varianten.map((v) => v.sku) : [p.sku])));

// Text für den Kunden, wenn die Menge nicht reicht
export function lagerFehler(rest, email) {
  return rest > 0
    ? `Nur ${rest} Stück sofort lieferbar. Für größere Mengen schreiben Sie uns bitte an ${email}, wir nennen Ihnen gern einen Liefertermin.`
    : `Diese Ausführung ist aktuell nicht verfügbar. Schreiben Sie uns an ${email}, wir sagen Ihnen, wann wir sie wieder haben.`;
}
