// KI-Berater: Claude bekommt den Katalog (nur Produkte mit Preis) und zeigt passende Produkte über ein Werkzeug an.
// Händler und Einkaufspreise kennt der Berater nicht; sie liegen nur im internen Speicher (siehe bestellung.js).
import Anthropic from "@anthropic-ai/sdk";
import KATALOG from "./katalog.json" with { type: "json" };

export const MODELL = "claude-opus-5-5";
const MAX_RUNDEN = 4;
const MAX_ANZEIGE = 4;

export const NACH_SKU = new Map(KATALOG.map((p) => [p.sku, p]));

function euro(x) {
  return x.toFixed(2).replace(".", ",") + " €";
}

function katalogZeile(p) {
  const merkmale = Object.entries(p.merkmale).map(([k, v]) => `${k}: ${v}`).join("; ");
  const preis = p.varianten.length
    ? p.varianten.map((v) => `${v.ausfuehrung} = ${euro(v.preis)}`).join(" | ")
    : (p.preis_ab ? "ab " : "") + euro(p.preis);
  return `- ${p.sku} | ${p.name}${p.marke ? ` (${p.marke})` : ""} | ${p.kurz} | ${merkmale} | Preis netto: ${preis}`;
}

const ANLEITUNG = `Sie sind der Produktberater von beinundfuß.de, einem Shop der TS Systemtechnik für Stellfüße, Stellbeine, Einschlagfüße, Gelenkfüße und Schwingungsdämpfer. Kunden sind meist Gewerbetreibende (Maschinenbau, Möbel, Regale, Gastronomie).

So beraten Sie:
- Antworten Sie auf Deutsch, kurz und freundlich, per Sie. Höchstens fünf Sätze pro Antwort, keine Tabellen.
- Fehlt Ihnen für eine sinnvolle Auswahl Wichtiges, fragen Sie gezielt nach, höchstens zwei Fragen auf einmal. Typisch: Anwendung, Gewinde oder Rohrmaß (rund/vierkant, Außenmaß), Last pro Fuß, Boden (eben, uneben, empfindlich, rutschig), Verstellweg, Umgebung (feucht, Lebensmittel, Vibration).
- Rechnen Sie bei Lastangaben die Last pro Fuß aus (Gesamtlast geteilt durch Anzahl Füße) und empfehlen Sie eine Reserve. Garantieren Sie keine Tragfähigkeit; verbindlich ist das Datenblatt des Herstellers.
- Empfehlen Sie ausschließlich Produkte aus dem Katalog unten. Erfinden Sie keine Produkte, Maße oder Preise.
- Sobald Sie passende Produkte nennen, rufen Sie das Werkzeug produkte_zeigen mit deren Artikelnummern auf (höchstens ${MAX_ANZEIGE}, bestes zuerst). Nur so sieht der Kunde die Produkte mit Bestellknopf. Sagen Sie im Text in einem Satz, warum Sie diese gewählt haben.
- Alle Preise sind netto zzgl. MwSt. und Versand. "ab"-Preise gelten für die günstigste Ausführung einer Serie; die genaue Ausführung bestätigen wir nach der Bestellung.
- Passt nichts im Katalog, sagen Sie das offen und verweisen Sie auf eine Anfrage per E-Mail an sales@ts-systec.de; dort sind auch Sonderanfertigungen und weitere Produkte ohne Online-Preis möglich.
- Bezugsquellen, Lieferanten oder Einkaufspreise kennen Sie nicht und spekulieren nicht darüber.
- Bleiben Sie beim Thema Maschinenfüße. Andere Anfragen lehnen Sie höflich ab.

Katalog (Artikelnummer | Name | Beschreibung | Merkmale | Preis):
`;

export const SYSTEM = ANLEITUNG + KATALOG.map(katalogZeile).join("\n");

export const WERKZEUGE = [
  {
    name: "produkte_zeigen",
    description:
      "Zeigt dem Kunden Produktkarten mit Bild, Preis und Bestellknopf. Nur Artikelnummern aus dem Katalog verwenden, höchstens " +
      MAX_ANZEIGE + ", das am besten passende zuerst.",
    strict: true,
    input_schema: {
      type: "object",
      properties: {
        artikelnummern: { type: "array", items: { type: "string" }, description: "Artikelnummern aus dem Katalog" },
      },
      required: ["artikelnummern"],
      additionalProperties: false,
    },
  },
];

// Was die Seite für eine Produktkarte braucht; alles davon ist ohnehin öffentlich.
export function karte(p) {
  return { sku: p.sku, name: p.name, marke: p.marke, kurz: p.kurz, merkmale: p.merkmale, preis: p.preis,
           preis_ab: p.preis_ab, varianten: p.varianten, bild: p.bild };
}

export function produkteZeigen(eingabe) {
  const nummern = Array.isArray(eingabe?.artikelnummern) ? eingabe.artikelnummern.filter((x) => typeof x === "string") : null;
  if (!nummern || !nummern.length) return { fehler: "artikelnummern fehlt oder ist leer" };
  const gefunden = [], unbekannt = [];
  for (const n of [...new Set(nummern)].slice(0, MAX_ANZEIGE)) (NACH_SKU.has(n) ? gefunden : unbekannt).push(n);
  if (!gefunden.length) return { fehler: `Unbekannte Artikelnummern: ${unbekannt.join(", ")}. Nur Nummern aus dem Katalog verwenden.` };
  return { karten: gefunden.map((n) => karte(NACH_SKU.get(n))), unbekannt };
}

// verlauf: [{rolle: "kunde"|"berater", text}] aus dem Browser; nur Text, keine Werkzeugblöcke.
export function nachrichtenAus(verlauf) {
  const messages = [];
  for (const m of verlauf) {
    const role = m.rolle === "berater" ? "assistant" : "user";
    if (!messages.length && role === "assistant") continue; // erste Nachricht muss vom Kunden sein
    messages.push({ role, content: m.text });
  }
  return messages;
}

export async function beraten(client, verlauf, modell = MODELL) {
  const messages = nachrichtenAus(verlauf);
  let karten = [];
  for (let runde = 0; runde < MAX_RUNDEN; runde++) {
    const antwort = await client.messages.create({
      model: modell,
      max_tokens: 4000,
      output_config: { effort: "low" }, // Chat: lieber schnell; Katalogauswahl braucht keine lange Denkzeit
      system: [{ type: "text", text: SYSTEM, cache_control: { type: "ephemeral", ttl: "1h" } }],
      tools: WERKZEUGE,
      messages,
    });
    const text = antwort.content.filter((b) => b.type === "text").map((b) => b.text).join("\n").trim();
    const aufrufe = antwort.content.filter((b) => b.type === "tool_use");
    if (antwort.stop_reason === "refusal") {
      return { antwort: "Dazu kann ich leider nicht helfen. Bei Fragen zu Stellfüßen und Einschlagfüßen bin ich gern da.", produkte: [] };
    }
    if (antwort.stop_reason !== "tool_use" || !aufrufe.length) {
      return { antwort: text || "Entschuldigung, da ist etwas schiefgelaufen. Bitte formulieren Sie Ihre Frage noch einmal.", produkte: karten };
    }
    messages.push({ role: "assistant", content: antwort.content });
    const ergebnisse = aufrufe.map((a) => {
      const r = a.name === "produkte_zeigen" ? produkteZeigen(a.input) : { fehler: `Unbekanntes Werkzeug ${a.name}` };
      if (r.karten) karten = [...karten, ...r.karten.filter((k) => !karten.some((x) => x.sku === k.sku))].slice(0, MAX_ANZEIGE);
      const inhalt = r.fehler
        ? r.fehler
        : `Dem Kunden angezeigt: ${r.karten.map((k) => k.sku).join(", ")}` + (r.unbekannt.length ? `. Unbekannt und nicht angezeigt: ${r.unbekannt.join(", ")}` : "");
      return { type: "tool_result", tool_use_id: a.id, content: inhalt, ...(r.fehler ? { is_error: true } : {}) };
    });
    messages.push({ role: "user", content: ergebnisse });
  }
  return { antwort: "Hier sind passende Produkte.", produkte: karten };
}

export function neuerClient(env) {
  return new Anthropic({ apiKey: env.ANTHROPIC_API_KEY, baseURL: env.ANTHROPIC_BASE_URL || undefined }); // BASE_URL nur für lokale Tests
}
