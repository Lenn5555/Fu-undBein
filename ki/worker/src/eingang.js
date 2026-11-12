// Morgendliche Lagerdatei per E-Mail (Lenn, 12.11.2026): Elisa schickt die Excel-Datei an lager@beinundfuss.de,
// Resend meldet die Mail per Webhook an /lager/eingang. Der Server prüft die Signatur, holt die Mail samt Anhang
// über die Resend-API (Schlüssel RESEND_LESEN_KEY), prüft Absender (nur die Adresse mit LAGER_ABSENDER_HASH)
// und Echtheit (SPF/DKIM) und ersetzt dann den Lagerbestand. Danach geht eine kurze Rückmeldung an den Absender.
import { xlsxZeilen, csvZeilen, bestandAus } from "./tabelle.js";
import { TS_ARTIKEL } from "./lagerkern.js";
import { mailHtml } from "./bestellung.js";

const API = "https://api.resend.com";

function b64(bytes) {
  let s = "";
  for (const x of new Uint8Array(bytes)) s += String.fromCharCode(x);
  return btoa(s);
}

// Webhook-Signatur nach dem Svix-Verfahren, das Resend verwendet
export async function signaturOk(secret, kopf, roh, jetzt = Date.now()) {
  const id = kopf.get("svix-id"), zeit = kopf.get("svix-timestamp"), sig = kopf.get("svix-signature");
  if (!secret || !id || !zeit || !sig) return false;
  if (Math.abs(jetzt / 1000 - Number(zeit)) > 300) return false;
  const schluessel = Uint8Array.from(atob(secret.replace(/^whsec_/, "")), (c) => c.charCodeAt(0));
  const k = await crypto.subtle.importKey("raw", schluessel, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const soll = b64(await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(`${id}.${zeit}.${roh}`)));
  return sig.split(" ").some((t) => t.split(",")[1] === soll);
}

export async function sha256(text) {
  const h = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(h)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

export function adresse(from) {
  const m = String(from || "").match(/<([^>]+)>/);
  return (m ? m[1] : String(from || "")).trim().toLowerCase();
}

async function api(env, pfad, abruf) {
  const r = await abruf(API + pfad, { headers: { Authorization: `Bearer ${env.RESEND_LESEN_KEY}` } });
  if (!r.ok) throw new Error(`Resend ${pfad.split("/").slice(0, 3).join("/")}: ${r.status}`);
  return r.json();
}

// Liest Tabelle aus Anhang; Ergebnis { liste, spalten, datei }
export async function tabelleLesen(name, inhalt) {
  if (/\.xlsx$/i.test(name)) return bestandAus(await xlsxZeilen(inhalt));
  if (/\.(csv|txt)$/i.test(name)) return bestandAus(csvZeilen(new TextDecoder().decode(inhalt)));
  throw new Error(`Dateityp nicht unterstützt: ${name} (bitte .xlsx oder .csv)`);
}

// Gleicht die gelesene Liste mit den T&S-Artikeln im Shop ab
export function abgleichen(liste) {
  const nachArtikel = new Map(liste.map((z) => [z.artikel, z.menge]));
  const treffer = [...TS_ARTIKEL].filter((a) => nachArtikel.has(a)).map((a) => ({ artikel: a, menge: nachArtikel.get(a) }));
  const fehlend = [...TS_ARTIKEL].filter((a) => !nachArtikel.has(a));
  return { treffer, fehlend };
}

async function antworten(env, an, betreff, text, abruf) {
  if (!env.KUNDEN_ABSENDER || !env.RESEND_API_KEY) return;
  await abruf(API + "/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({ from: env.KUNDEN_ABSENDER, to: [an], subject: betreff, text, html: mailHtml(text) }),
  }).catch((e) => console.error("Lager-Rückmeldung:", e.message));
}

export async function lagerEingang(request, env, lager, abruf = fetch) {
  const roh = await request.text();
  if (!(await signaturOk(env.RESEND_WEBHOOK_SECRET, request.headers, roh))) return { status: 401, text: "Signatur ungültig" };
  let ereignis;
  try { ereignis = JSON.parse(roh); } catch { return { status: 400, text: "Ungültig" }; }
  if (ereignis.type !== "email.received") return { status: 200, text: "ignoriert" };
  const id = ereignis.data?.email_id;
  if (!id || !env.RESEND_LESEN_KEY || !lager) return { status: 200, text: "nicht eingerichtet" };

  const mail = await api(env, `/emails/receiving/${encodeURIComponent(id)}`, abruf);
  const von = adresse(mail.headers?.from || mail.from);
  if ((await sha256(von)) !== env.LAGER_ABSENDER_HASH) {
    console.log("Lagerdatei von nicht freigegebenem Absender verworfen");
    return { status: 200, text: "Absender nicht freigegeben" };
  }
  const auth = mail.authentication || {};
  if (auth.dkim !== "pass" && auth.spf !== "pass") {
    console.log("Lagerdatei verworfen: SPF/DKIM nicht bestanden", JSON.stringify(auth));
    return { status: 200, text: "Echtheit nicht bestätigt" };
  }
  const anh = await api(env, `/emails/receiving/${encodeURIComponent(id)}/attachments`, abruf);
  const datei = (anh.data || []).find((a) => /\.(xlsx|csv)$/i.test(a.filename || ""));
  if (!datei) {
    await antworten(env, von, "Lagerbestand NICHT übernommen", "Ihre Mail an lager@ hatte keine Excel-Datei (.xlsx) oder CSV im Anhang. Der Lagerbestand im Shop ist unverändert.", abruf);
    return { status: 200, text: "kein Anhang" };
  }
  try {
    const r = await abruf(datei.download_url);
    if (!r.ok) throw new Error(`Download ${r.status}`);
    const { liste, spalten } = await tabelleLesen(datei.filename, await r.arrayBuffer());
    if (!spalten) throw new Error("Keine Spalten für Artikelnummer und Bestand gefunden.");
    const { treffer, fehlend } = abgleichen(liste);
    if (!treffer.length) throw new Error("Keine der Artikelnummern passt zu den T&S-Artikeln im Shop.");
    const stand = new Date().toISOString();
    await lager.setzen(treffer, stand, datei.filename);
    const leer = treffer.filter((z) => z.menge === 0).map((z) => z.artikel);
    console.log(`Lagerbestand übernommen: ${treffer.length} Artikel aus ${datei.filename}`);
    await antworten(env, von, "Lagerbestand übernommen", [
      `Der Lagerbestand aus „${datei.filename}“ ist im Shop übernommen.`,
      ``,
      `Gelesen: Spalte „${spalten.artikel}“ als Artikelnummer, „${spalten.bestand}“ als Bestand.`,
      `Übernommen: ${treffer.length} von ${TS_ARTIKEL.size} T&S-Artikeln im Shop.`,
      leer.length ? `Aktuell nicht verfügbar (Bestand 0): ${leer.join(", ")}` : `Alle übernommenen Artikel sind auf Lager.`,
      fehlend.length ? `Nicht in der Datei (im Shop ohne Bestandsanzeige, bestellbar): ${fehlend.join(", ")}` : ``,
    ].join("\n"), abruf);
    return { status: 200, text: "ok" };
  } catch (err) {
    console.error("Lagerdatei:", err.message);
    await antworten(env, von, "Lagerbestand NICHT übernommen",
      `Die Datei „${datei.filename}“ konnte nicht übernommen werden: ${err.message}\nDer Lagerbestand im Shop ist unverändert.`, abruf);
    return { status: 200, text: "Fehler" };
  }
}
