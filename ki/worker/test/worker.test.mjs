import { test } from "node:test";
import assert from "node:assert/strict";
import { beraten, produkteZeigen, nachrichtenAus, SYSTEM } from "../src/berater.js";
import { pruefen, mailText, mailHtml, senden } from "../src/bestellung.js";
import KATALOG from "../src/katalog.json" with { type: "json" };

// Unterschiebbarer Client: gibt vorbereitete Antworten zurück und merkt sich die Anfragen.
function falscherClient(antworten) {
  const anfragen = [];
  return { anfragen, messages: { create: async (a) => { anfragen.push(structuredClone(a)); return antworten.shift(); } } };
}

test("Katalog enthält nur Produkte mit Preis und keine internen Daten", () => {
  assert.ok(KATALOG.length > 200);
  for (const p of KATALOG) assert.ok(p.preis || p.varianten.length, p.sku);
  const roh = JSON.stringify(KATALOG) + SYSTEM;
  for (const wort of ["ek_netto", "bezugsquelle", "bestell_url", "preis_quelle"]) assert.ok(!roh.includes(wort), wort);
});

test("produkte_zeigen filtert unbekannte Nummern und begrenzt auf 4", () => {
  const nr = KATALOG.slice(0, 6).map((p) => p.sku);
  const r = produkteZeigen({ artikelnummern: [...nr, "GIBTSNICHT"] });
  assert.equal(r.karten.length, 4);
  assert.ok(produkteZeigen({ artikelnummern: ["GIBTSNICHT"] }).fehler);
  assert.ok(produkteZeigen({}).fehler);
});

test("Verlauf beginnt immer mit dem Kunden", () => {
  const m = nachrichtenAus([{ rolle: "berater", text: "Hallo" }, { rolle: "kunde", text: "M10" }]);
  assert.deepEqual(m, [{ role: "user", content: "M10" }]);
});

test("Beraterschleife: Werkzeug, Ergebnis, Abschlusstext", async () => {
  const [a, b] = KATALOG;
  const client = falscherClient([
    { stop_reason: "tool_use", content: [{ type: "text", text: "Moment." },
      { type: "tool_use", id: "t1", name: "produkte_zeigen", input: { artikelnummern: [a.sku, "X", b.sku] } }] },
    { stop_reason: "end_turn", content: [{ type: "text", text: "Diese beiden passen." }] },
  ]);
  const r = await beraten(client, [{ rolle: "kunde", text: "Ich brauche Füße M10" }]);
  assert.equal(r.antwort, "Diese beiden passen.");
  assert.deepEqual(r.produkte.map((k) => k.sku), [a.sku, b.sku]);
  assert.equal(client.anfragen.length, 2);
  const erste = client.anfragen[0];
  assert.equal(erste.model, "claude-opus-5-5");
  assert.equal(erste.system[0].cache_control.type, "ephemeral");
  const ergebnis = client.anfragen[1].messages.at(-1).content[0];
  assert.equal(ergebnis.type, "tool_result");
  assert.match(ergebnis.content, /Unbekannt und nicht angezeigt: X/);
});

test("Leere letzte Runde: Text aus der Werkzeugrunde wird die Antwort", async () => {
  const [a] = KATALOG;
  const client = falscherClient([
    { stop_reason: "tool_use", content: [{ type: "text", text: "Für 400 kg auf vier Füßen passt dieser Fuß." },
      { type: "tool_use", id: "t1", name: "produkte_zeigen", input: { artikelnummern: [a.sku] } }] },
    { stop_reason: "end_turn", content: [] },
  ]);
  const r = await beraten(client, [{ rolle: "kunde", text: "Stellfuß M12, 400 kg" }]);
  assert.equal(r.antwort, "Für 400 kg auf vier Füßen passt dieser Fuß.");
  assert.deepEqual(r.produkte.map((k) => k.sku), [a.sku]);
});

test("Ablehnung führt zu freundlicher Absage ohne Produkte", async () => {
  const client = falscherClient([{ stop_reason: "refusal", content: [] }]);
  const r = await beraten(client, [{ rolle: "kunde", text: "..." }]);
  assert.deepEqual(r.produkte, []);
});

const KUNDE = { name: "Max Muster", email: "max@example.com", adresse: "Weg 1, 12345 Ort", zustimmung: true };

test("Bestellung prüfen: Varianten, Menge, Pflichtfelder, Falle", () => {
  const mitVar = KATALOG.find((p) => p.varianten.length);
  const ohne = KATALOG.find((p) => !p.varianten.length && !Object.keys(p.optionen || {}).length);
  assert.match(pruefen({ ...KUNDE, sku: mitVar.sku, menge: 2 }).fehler, /Ausführung/);
  const ok = pruefen({ ...KUNDE, sku: mitVar.sku, variante: mitVar.varianten[1].sku, menge: 3 });
  assert.equal(ok.summe, Math.round(mitVar.varianten[1].preis * 300) / 100);
  assert.ok(pruefen({ ...KUNDE, sku: ohne.sku, menge: 0 }).fehler);
  assert.ok(pruefen({ ...KUNDE, sku: ohne.sku, menge: 1, email: "kaputt" }).fehler);
  assert.ok(pruefen({ ...KUNDE, sku: ohne.sku, menge: 1, zustimmung: false }).fehler);
  assert.ok(pruefen({ ...KUNDE, sku: ohne.sku, menge: 1, website: "spam" }).fehler);
  assert.ok(pruefen({ ...KUNDE, sku: "GIBTSNICHT", menge: 1 }).fehler);
});

test("Bestellmail enthält Bezugsquelle, EK und Aufschlag", async () => {
  const p = KATALOG.find((p) => !p.varianten.length && !Object.keys(p.optionen || {}).length);
  const b = pruefen({ ...KUNDE, sku: p.sku, menge: 10 });
  const text = mailText("BF-1", b, { bezugsquelle: "Händler X", bestell_url: "https://x.example/a", ek_netto: p.preis / 1.1, hersteller: "H" });
  assert.match(text, /Bezugsquelle: Händler X/);
  assert.match(text, /Bestell-Link: https:\/\/x\.example\/a/);
  assert.match(text, /Aufschlag gesamt/);
  assert.match(mailText("BF-2", b, null), /Keine Bezugsquelle hinterlegt/);
  let gesendet;
  await senden({ RESEND_API_KEY: "k", ABSENDER: "a@b.de", BESTELL_EMAIL: "sales@ts-systec.de" }, "BF-1", b, text,
    async (url, opt) => { gesendet = JSON.parse(opt.body); return { ok: true }; });
  assert.deepEqual(gesendet.to, ["sales@ts-systec.de"]);
  assert.equal(gesendet.reply_to, "max@example.com");
  assert.match(gesendet.html, /Bezugsquelle: Händler X/);
  assert.match(gesendet.html, /<a href="https:\/\/x\.example\/a">/);
  assert.doesNotMatch(mailHtml("<b>"), /<b>/);
});

test("Wählbares Gewinde wird geprüft und steht in der Bestellmail", () => {
  const p = KATALOG.find((p) => Object.keys(p.optionen || {}).length);
  assert.ok(p, "Katalog enthält Serien mit wählbarem Gewinde");
  const werte = p.optionen.Gewinde;
  assert.match(pruefen({ ...KUNDE, sku: p.sku, menge: 2 }).fehler, /Gewinde/);
  assert.match(pruefen({ ...KUNDE, sku: p.sku, menge: 2, optionen: { Gewinde: "M999" } }).fehler, /Gewinde/);
  const b = pruefen({ ...KUNDE, sku: p.sku, menge: 2, optionen: { Gewinde: werte[1] }, wunsch: "Länge 125 mm" });
  assert.ok(!b.fehler, b.fehler);
  const text = mailText("BF-3", b, null);
  assert.match(text, new RegExp(`BESTELLTE AUSFÜHRUNG: Gewinde ${werte[1]}`));
  assert.match(text, /Wunsch des Kunden zur Ausführung: Länge 125 mm/);
  assert.match(text, new RegExp(`Kennung: ${p.sku}\\|Gewinde=${werte[1]}`));
});

test("Gewählte Variante steht mit Artikelnummer in der Bestellmail", () => {
  const p = KATALOG.find((p) => p.varianten.length > 1);
  const v = p.varianten[1];
  const b = pruefen({ ...KUNDE, sku: p.sku, variante: v.sku, menge: 3 });
  assert.equal(b.stueck, v.preis);
  const text = mailText("BF-4", b, null);
  assert.match(text, new RegExp(`BESTELLTE AUSFÜHRUNG: .*Artikelnummer ${v.sku}`));
  assert.match(text, new RegExp(`Kennung: ${v.sku}`));
});

test("Bezugsquelle kommt aus der mitgelieferten Datei", async () => {
  const { bezugsquelle } = await import("../src/bestellung.js");
  assert.equal(bezugsquelle("GIBTSNICHT"), null);
});

test("Lieferland und USt-IdNr.: EU-Ausland nur mit USt-IdNr., Nicht-EU mit Hinweis", () => {
  const p = KATALOG.find((p) => !p.varianten.length && !Object.keys(p.optionen || {}).length);
  const basis = { ...KUNDE, sku: p.sku, menge: 1 };
  const inland = pruefen(basis);
  assert.ok(!inland.fehler, inland.fehler);
  assert.match(mailText("BF-5", inland, null), /Lieferland: Deutschland/);
  assert.doesNotMatch(mailText("BF-5", inland, null), /AUSLANDSBESTELLUNG/);
  assert.match(pruefen({ ...basis, land: "Österreich" }).fehler, /USt-IdNr/);
  assert.match(pruefen({ ...basis, land: "Atlantis" }).fehler, /Lieferland/);
  const at = pruefen({ ...basis, land: "Österreich", ust_id: "atu 1234 5678" });
  assert.ok(!at.fehler, at.fehler);
  const mail = mailText("BF-6", at, null);
  assert.match(mail, /Lieferland: Österreich/);
  assert.match(mail, /USt-IdNr\.: ATU12345678/);
  assert.match(mail, /AUSLANDSBESTELLUNG: EU, ohne deutsche MwSt/);
  const ch = pruefen({ ...basis, land: "Schweiz" });
  assert.ok(!ch.fehler, ch.fehler);
  assert.match(mailText("BF-7", ch, null), /Nicht-EU: Zoll/);
});

test("Bestellung: Zahlung nur Vorkasse, Zahlungsart aus der Liste", () => {
  const p = KATALOG.find((x) => !x.varianten.length && !Object.keys(x.optionen || {}).length);
  const basis = { sku: p.sku, menge: 2, name: "Max", email: "max@example.com", adresse: "Weg 1", zustimmung: true };
  const ohne = pruefen(basis);
  assert.equal(ohne.kunde.zahlart, "Überweisung (Vorkasse)");
  assert.match(mailText("BF-8", ohne, null), /ZAHLUNG: Vorkasse per Überweisung \(Vorkasse\)/);
  assert.match(mailText("BF-9", pruefen({ ...basis, zahlart: "PayPal" }), null), /Vorkasse per PayPal/);
  assert.match(pruefen({ ...basis, zahlart: "Rechnung" }).fehler, /Zahlungsart/);
});

test("Zählung: nur erlaubte Ereignisse und Quellen, Einstieg nur beim Besuch", async () => {
  const { meldungPruefen } = await import("../src/statistik.js");
  assert.equal(meldungPruefen({ ereignis: "hack" }), null);
  assert.equal(meldungPruefen(null), null);
  assert.deepEqual(meldungPruefen({ ereignis: "chat_start", quelle: "boese" }), [{ art: "ereignis", wert: "chat_start", quelle: "direkt" }]);
  const b = meldungPruefen({ ereignisse: ["seitenaufruf", "besuch", "besuch"], quelle: "werbung", seite: "produkt" });
  assert.deepEqual(b, [
    { art: "ereignis", wert: "seitenaufruf", quelle: "werbung" },
    { art: "ereignis", wert: "besuch", quelle: "werbung" },
    { art: "einstieg", wert: "produkt", quelle: "werbung" },
  ]);
  // „bestellung“ zählt nur der Server
  assert.equal(meldungPruefen({ ereignis: "bestellung" }), null);
});

test("Statistik: Bericht und Schlüssel", async () => {
  const { bericht, schluesselPasst } = await import("../src/statistik.js");
  const r = bericht([
    { tag: "2026-10-22", art: "ereignis", wert: "besuch", quelle: "werbung", n: 3 },
    { tag: "2026-10-22", art: "ereignis", wert: "besuch", quelle: "google", n: 5 },
    { tag: "2026-10-22", art: "ereignis", wert: "bestellung", quelle: "werbung", n: 1 },
    { tag: "2026-10-21", art: "einstieg", wert: "produkt", quelle: "google", n: 2 },
    { tag: "2026-10-21", art: "luecke", wert: "Stellfuß: Traglast zu hoch", quelle: "berater", n: 4 },
  ], 7);
  assert.equal(r.summe.besuch, 8);
  assert.equal(r.werbung.besuch, 3);
  assert.equal(r.werbung.bestellung, 1);
  assert.deepEqual(r.quellen, { werbung: 3, google: 5 });
  assert.equal(r.proTag["2026-10-22"].besuch, 8);
  assert.equal(r.einstieg.produkt, 2);
  assert.equal(r.luecken["Stellfuß: Traglast zu hoch"], 4);
  assert.deepEqual(r.umsatz, { netto_cent: 0, werbung_cent: 0, proTag: {} });
  // sha256("test")
  assert.ok(await schluesselPasst("test", "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"));
  assert.ok(!(await schluesselPasst("falsch", "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08")));
  assert.ok(!(await schluesselPasst("", "")));
});

test("Berater meldet „nichts passend“ nur als Kategorie", async () => {
  const client = falscherClient([
    { stop_reason: "tool_use", content: [{ type: "text", text: "Dafür haben wir leider nichts." },
      { type: "tool_use", id: "t1", name: "nichts_passend", input: { bauform: "Stellfuß", grund: "Traglast zu hoch" } }] },
    { stop_reason: "end_turn", content: [{ type: "text", text: "Schreiben Sie uns gern." }] },
  ]);
  const r = await beraten(client, [{ rolle: "kunde", text: "Fuß für 20 Tonnen, Firma Muster" }]);
  assert.equal(r.luecke, "Stellfuß: Traglast zu hoch");
  assert.deepEqual(r.produkte, []);
  assert.equal(client.anfragen[1].messages.at(-1).content[0].content, "Notiert.");
  // Ungültige Kategorien werden nicht gezählt
  const c2 = falscherClient([
    { stop_reason: "tool_use", content: [{ type: "tool_use", id: "t1", name: "nichts_passend", input: { bauform: "Firma Muster", grund: "x" } }] },
    { stop_reason: "end_turn", content: [{ type: "text", text: "Ok." }] },
  ]);
  assert.equal((await beraten(c2, [{ rolle: "kunde", text: "?" }])).luecke, null);
});

test("Statistik: Bestellung zählt nur Summen aus Katalogpreis und Menge", async () => {
  const { bestellEintraege, bericht } = await import("../src/statistik.js");
  const b = { produkt: { sku: "A-1", name: "Stellfuß M10" }, menge: 4, summe: 12.34, kunde: { name: "Muster", email: "a@b.de" } };
  const e = bestellEintraege({ herkunft: "werbung", summe: 999999 }, b);
  assert.deepEqual(e, [
    { art: "ereignis", wert: "bestellung", quelle: "werbung" },
    { art: "umsatz", wert: "netto_cent", quelle: "werbung", n: 1234 },
    { art: "artikel", wert: "A-1 Stellfuß M10", quelle: "werbung", n: 4 },
  ]);
  assert.ok(!JSON.stringify(e).includes("Muster"));
  const r = bericht([
    ...e.map((x) => ({ tag: "2026-10-22", ...x, n: x.n ?? 1 })),
    { tag: "2026-10-23", art: "umsatz", wert: "netto_cent", quelle: "sonstige", n: 500 },
    { tag: "2026-10-23", art: "artikel", wert: "A-1 Stellfuß M10", quelle: "sonstige", n: 2 },
  ], 7);
  assert.deepEqual(r.umsatz, { netto_cent: 1734, werbung_cent: 1234, proTag: { "2026-10-22": 1234, "2026-10-23": 500 } });
  assert.equal(r.artikel["A-1 Stellfuß M10"], 6);
  assert.equal(r.summe.bestellung, 1);
});
