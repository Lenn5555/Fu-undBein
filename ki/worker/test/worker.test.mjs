import { test } from "node:test";
import assert from "node:assert/strict";
import { beraten, produkteZeigen, nachrichtenAus, SYSTEM } from "../src/berater.js";
import { pruefen, mailText, senden } from "../src/bestellung.js";
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

test("Ablehnung führt zu freundlicher Absage ohne Produkte", async () => {
  const client = falscherClient([{ stop_reason: "refusal", content: [] }]);
  const r = await beraten(client, [{ rolle: "kunde", text: "..." }]);
  assert.deepEqual(r.produkte, []);
});

const KUNDE = { name: "Max Muster", email: "max@example.com", adresse: "Weg 1, 12345 Ort", zustimmung: true };

test("Bestellung prüfen: Varianten, Menge, Pflichtfelder, Falle", () => {
  const mitVar = KATALOG.find((p) => p.varianten.length);
  const ohne = KATALOG.find((p) => !p.varianten.length);
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
  const p = KATALOG.find((p) => !p.varianten.length);
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
});
