// Liest die Lager-Tabelle aus einer Excel-Datei (.xlsx) oder CSV, ohne Fremdbibliothek.
// .xlsx ist ein ZIP-Archiv mit XML-Dateien; gelesen wird das erste Tabellenblatt.

async function entpacken(daten, methode) {
  if (methode === 0) return daten;
  if (methode !== 8) throw new Error("Unbekannte Kompression in der Excel-Datei.");
  const strom = new Blob([daten]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
  return new Uint8Array(await new Response(strom).arrayBuffer());
}

// Liefert { name: Uint8Array } für die gewünschten Dateien aus dem ZIP
export async function zipLesen(buf, gesucht) {
  const b = new Uint8Array(buf), dv = new DataView(b.buffer, b.byteOffset, b.byteLength);
  let ende = -1;
  for (let i = b.length - 22; i >= Math.max(0, b.length - 65557); i--) if (dv.getUint32(i, true) === 0x06054b50) { ende = i; break; }
  if (ende < 0) throw new Error("Keine gültige Excel-Datei.");
  const anzahl = dv.getUint16(ende + 10, true);
  let p = dv.getUint32(ende + 16, true);
  const raus = {};
  const dec = new TextDecoder();
  for (let n = 0; n < anzahl; n++) {
    if (dv.getUint32(p, true) !== 0x02014b50) break;
    const methode = dv.getUint16(p + 10, true), groesse = dv.getUint32(p + 20, true);
    const lName = dv.getUint16(p + 28, true), lExtra = dv.getUint16(p + 30, true), lKomm = dv.getUint16(p + 32, true);
    const lokal = dv.getUint32(p + 42, true);
    const name = dec.decode(b.subarray(p + 46, p + 46 + lName));
    if (gesucht(name)) {
      const start = lokal + 30 + dv.getUint16(lokal + 26, true) + dv.getUint16(lokal + 28, true);
      raus[name] = await entpacken(b.subarray(start, start + groesse), methode);
    }
    p += 46 + lName + lExtra + lKomm;
  }
  return raus;
}

function xmlText(s) {
  return s.replace(/<[^>]+>/g, "").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&apos;/g, "'")
    .replace(/&#(\d+);/g, (_, d) => String.fromCharCode(+d)).replace(/&amp;/g, "&");
}

function spalte(ref) {
  let n = 0;
  for (const c of ref.replace(/\d+/g, "")) n = n * 26 + (c.charCodeAt(0) - 64);
  return n - 1;
}

// Zeilen als Arrays von Texten
export async function xlsxZeilen(buf) {
  const d = await zipLesen(buf, (n) => n === "xl/sharedStrings.xml" || /^xl\/worksheets\/sheet\d+\.xml$/.test(n));
  const dec = new TextDecoder();
  const texte = d["xl/sharedStrings.xml"]
    ? [...dec.decode(d["xl/sharedStrings.xml"]).matchAll(/<si>([\s\S]*?)<\/si>/g)].map((m) =>
        xmlText([...m[1].matchAll(/<t[^>]*>([\s\S]*?)<\/t>/g)].map((t) => t[1]).join("")))
    : [];
  const blatt = Object.keys(d).filter((n) => n.startsWith("xl/worksheets/")).sort((a, b) => parseInt(a.match(/\d+/)) - parseInt(b.match(/\d+/)))[0];
  if (!blatt) throw new Error("Kein Tabellenblatt in der Excel-Datei.");
  const xml = dec.decode(d[blatt]);
  const zeilen = [];
  for (const r of xml.matchAll(/<row[^>]*>([\s\S]*?)<\/row>/g)) {
    const z = [];
    for (const c of r[1].matchAll(/<c([^>]*?)(?:\/>|>([\s\S]*?)<\/c>)/g)) {
      const attr = c[1], inhalt = c[2] || "";
      const ref = (attr.match(/\br="([A-Z]+)\d+"/) || [])[1];
      const typ = (attr.match(/\bt="(\w+)"/) || [])[1];
      const v = (inhalt.match(/<v>([\s\S]*?)<\/v>/) || [])[1];
      let wert = "";
      if (typ === "s") wert = texte[+v] ?? "";
      else if (typ === "inlineStr") wert = xmlText((inhalt.match(/<is>([\s\S]*?)<\/is>/) || [])[1] || "");
      else if (v !== undefined) wert = xmlText(v);
      z[ref ? spalte(ref) : z.length] = wert.trim();
    }
    zeilen.push(Array.from(z, (x) => x ?? ""));
  }
  return zeilen;
}

export function csvZeilen(text) {
  const erste = text.split(/\r?\n/)[0] || "";
  const trenner = (erste.match(/;/g) || []).length >= (erste.match(/,/g) || []).length ? ";" : ",";
  return text.split(/\r?\n/).filter((z) => z.trim()).map((z) => z.split(trenner).map((x) => x.replace(/^"|"$/g, "").trim()));
}

const ARTIKEL_KOPF = /^(art(ikel)?[ .-]*(nr|nummer|no)\.?|artikel|itemcode|item ?no|material(nummer)?|sku|teilenummer)$/i;
const BESTAND_KOPF = /(bestand|lager|verfügbar|verfuegbar|auf lager|onhand|on hand|instock|in stock|menge|qty|stück)/i;

// Findet Kopfzeile und Spalten; liefert [{ artikel, menge }] und Hinweise
export function bestandAus(zeilen) {
  for (let i = 0; i < Math.min(zeilen.length, 20); i++) {
    const kopf = zeilen[i].map((x) => String(x).trim());
    const a = kopf.findIndex((x) => ARTIKEL_KOPF.test(x));
    // Bevorzugt „verfügbar“, sonst „Bestand“/„Lager“, sonst „Menge“
    const kandidaten = kopf.map((x, j) => [x, j]).filter(([x]) => BESTAND_KOPF.test(x));
    const rang = ([x]) => (/verfügbar|verfuegbar/i.test(x) ? 0 : /bestand|lager|on ?hand|in ?stock/i.test(x) ? 1 : 2);
    const m = kandidaten.sort((x, y) => rang(x) - rang(y))[0];
    if (a < 0 || !m) continue;
    const liste = [];
    for (const z of zeilen.slice(i + 1)) {
      const artikel = String(z[a] ?? "").trim();
      if (!artikel) continue;
      const roh = String(z[m[1]] ?? "").trim().replace(/\s/g, "");
      // deutsch „1.234,5“ oder englisch „1,234.5“ bzw. Zahl aus der Zelle
      const zahl = Number(/,\d+$/.test(roh) ? roh.replace(/\./g, "").replace(",", ".") : roh.replace(/,/g, ""));
      if (!Number.isFinite(zahl)) continue;
      liste.push({ artikel, menge: Math.max(0, Math.floor(zahl)) });
    }
    return { liste, spalten: { artikel: kopf[a], bestand: m[0] } };
  }
  return { liste: [], spalten: null };
}
