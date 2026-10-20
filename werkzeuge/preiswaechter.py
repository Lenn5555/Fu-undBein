#!/usr/bin/env python3
"""Preiswächter: prüft täglich die Händlerseiten der Bezugsquellen auf Preisänderungen und ausgelaufene Produkte.

Liest
  bezugsquellen.json        Händler, Bestell-Link und EK je Artikelnummer (aus dem GitHub-Secret BEZUGSQUELLEN,
                            nie im Repo; Pfad als Argument oder Umgebungsvariable BEZUGSQUELLEN_DATEI)
  daten/preise-vergleich.csv  aktuelle Verkaufspreise (EK + Aufschlag)
  daten/preiswaechter.json    Stand des Wächters: wie der Preis je Artikel auf der Händlerseite gefunden wird
Schreibt
  daten/preise-vergleich.csv, daten/ausgeblendet.csv, daten/preiswaechter.json
  bericht.txt               Bericht für die Mail (enthält Händlernamen; nur per Mail versenden, nie ins Log)

Grundsätze
  - Ins Log (öffentlich!) kommen nur Zahlen, nie Händler, Links oder Einkaufspreise.
  - Erster Lauf je Artikel = Einmessen: Nur wenn ein Leseweg den bekannten EK wiederfindet, wird der Artikel
    künftig automatisch geprüft. Sonst steht er einmal als „nicht automatisch prüfbar“ im Bericht.
  - Ausgeblendet wird nur bei eindeutigem Zeichen (Seite weg, Artikelnummer verschwunden, „nicht mehr lieferbar“)
    an zwei Läufen hintereinander. „Ausverkauft“ wird nur gemeldet.
  - Bremsen: Ist die Hälfte der Seiten nicht erreichbar oder wären auf einen Schlag viele Artikel betroffen,
    wird nichts geändert, nur gemeldet.

Aufruf: python3 werkzeuge/preiswaechter.py bezugsquellen.json [--nur-melden] [--ohne-bremse]

Je Artikelnummer gibt es eine Bezugsquelle mit einem Referenzpreis (bei Serien die günstigste Ausführung,
siehe preis_bezug). Danach richtet sich der „ab“-Preis im Shop; einzelne Gewinde haben keinen eigenen Preis.
"""
import csv
import gzip
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
PREISE = ROOT / "daten/preise-vergleich.csv"
AUSGEBLENDET = ROOT / "daten/ausgeblendet.csv"
STAND = ROOT / "daten/preiswaechter.json"

AUFSCHLAG = 1.10            # Verkaufspreis = EK + 10 % (Lenn, 08.10.2026)
MWST = 1.19
TOLERANZ_EINMESSEN = 0.03   # gefundener Preis darf beim Einmessen 3 % vom bekannten EK abweichen
MAX_SPRUNG = 0.25           # größere Preissprünge nur melden, nicht übernehmen
MAX_AUSBLENDEN = 5          # mehr auf einmal = verdächtig, dann nur melden
MAX_PREISAENDERUNGEN = 40
MIN_ERREICHBAR = 0.5        # Anteil erreichbarer Seiten, darunter wird nichts geändert
PAUSE = 1.5                 # Sekunden zwischen zwei Abrufen

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"

AUSLAUF = re.compile(r"nicht mehr (?:lieferbar|verfügbar|erhältlich)|ausgelaufen|auslaufartikel|no longer available|discontinued"
                     r"|nicht mehr im sortiment|produkt wurde nicht gefunden|artikel (?:ist )?nicht (?:mehr )?verfügbar", re.I)
AUSVERKAUFT = re.compile(r"ausverkauft|sold out|out of stock|nicht auf lager|derzeit nicht lieferbar|vorübergehend nicht", re.I)
SPERRSEITE = re.compile(r"captcha|just a moment|access denied|zugriff verweigert|are you a (?:human|robot)|checking your browser"
                        r"|request blocked|attention required|enable javascript and cookies", re.I)
PREIS = re.compile(r"(?:€|EUR)\s*(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})(?!\d)|(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})\s*(?:€|EUR)", re.I)


# ---------------------------------------------------------------- Seite lesen

def zahl(text):
    """'1.234,56' / '1,234.56' / '29.01' / '3,71' -> float"""
    t = text.replace(" ", "").replace(" ", "")
    dez = max(t.rfind(","), t.rfind("."))
    ganz = re.sub(r"[.,]", "", t[:dez])
    return float(f"{ganz}.{t[dez + 1:]}")


def sichtbarer_text(roh):
    t = re.sub(r"(?is)<(script|style|noscript|svg)\b.*?</\1>", " ", roh)
    t = re.sub(r"(?s)<!--.*?-->", " ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def preise_im_text(text, start=0, ende=None):
    werte = []
    for m in PREIS.finditer(text, start, len(text) if ende is None else ende):
        w = zahl(m.group(1) or m.group(2))
        if w > 0:
            werte.append(w)
    return werte


def jsonld_preise(roh):
    werte = []
    for block in re.findall(r'(?is)<script[^>]+application/ld\+json[^>]*>(.*?)</script>', roh):
        try:
            daten = json.loads(block.strip())
        except ValueError:
            continue
        stapel = [daten]
        while stapel:
            x = stapel.pop()
            if isinstance(x, list):
                stapel += x
            elif isinstance(x, dict):
                for k in ("price", "lowPrice"):
                    if k in x:
                        try:
                            werte.append(float(str(x[k]).replace(",", ".")))
                        except ValueError:
                            pass
                stapel += [v for v in x.values() if isinstance(v, (dict, list))]
    return werte


def meta_preise(roh):
    werte = []
    for m in re.finditer(r'(?i)<meta[^>]+(?:itemprop="price"|property="(?:product|og):price:amount")[^>]*>', roh):
        c = re.search(r'content="([\d.,]+)"', m.group(0))
        if c:
            try:
                werte.append(zahl(c.group(1)) if re.search(r"[.,]\d{2}$", c.group(1)) else float(c.group(1)))
            except ValueError:
                pass
    return werte


def merkmale(eintrag):
    """Artikelnummern aus den internen Angaben, nach denen auf der Seite gesucht wird (Reihenfolge fest)."""
    quelle = " ".join(str(eintrag.get(k) or "") for k in ("preis_bezug", "artikel"))
    quelle += " " + urlparse(eintrag.get("bestell_url") or "").path.rstrip("/").rsplit("/", 1)[-1]
    gefunden = []
    for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9.\-/]*[A-Za-z0-9]", quelle):
        if len(t) >= 5 and re.search(r"\d", t) and sum(c.isdigit() for c in t) >= 4 and t not in gefunden:
            gefunden.append(t)
    gefunden.sort(key=lambda t: -sum(c.isdigit() for c in t))  # genaueste Nummer zuerst
    return gefunden[:8]


def finde(text, token):
    """Position des Tokens; bei reinen Ziffern auch mit Trennzeichen (2378166 ~ 237-8166)."""
    i = text.find(token)
    if i >= 0:
        return i
    if token.isdigit() and len(token) >= 6:
        m = re.search(r"(?<!\d)" + r"[\s.\-]?".join(token) + r"(?!\d)", text)
        if m:
            return m.start()
    return -1


def kandidaten(roh, text, tokens):
    """Alle Lesewege mit ihrem Ergebnis. Schlüssel sind allgemein (keine Händlerangaben)."""
    k = {}
    j = jsonld_preise(roh)
    if j:
        k["jsonld"] = j[0]
        k["jsonld_min"] = min(j)
    m = meta_preise(roh)
    if m:
        k["meta"] = m[0]
    for n, t in enumerate(tokens):
        i = finde(text, t)
        if i >= 0:
            w = preise_im_text(text, i, i + 700)
            if w:
                k[f"nach:{n}"] = w[0]
    return k


def passt(wert, ek):
    if not ek:
        return None
    for brutto, faktor in ((False, 1.0), (True, MWST)):
        if abs(wert / faktor - ek) <= ek * TOLERANZ_EINMESSEN:
            return brutto
    return None


def lesen(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "de-DE,de;q=0.9,en;q=0.5",
                                               "Accept": "text/html,application/xhtml+xml,*/*;q=0.8", "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            return r.status, r.geturl(), body.decode(r.headers.get_content_charset() or "utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, url, ""
    except Exception:
        return 0, url, ""


# ---------------------------------------------------------------- Bewertung

def pruefe(eintrag, status, final, roh, basis):
    """Ergebnis für einen Artikel. art: ok, eingemessen, weg, auslauf, unlesbar, fehler, nicht_pruefbar.

    basis = Stand des Artikels aus dem letzten Lauf (Leseweg, Artikelnummer, ob „nicht mehr lieferbar“ schon dastand).
    """
    url = eintrag["bestell_url"]
    if status in (404, 410):
        return {"art": "weg", "grund": f"Händlerseite meldet {status} (nicht mehr vorhanden)"}
    if status != 200 or not roh:
        return {"art": "fehler"}
    if urlparse(final).path.rstrip("/") in ("", "/de", "/en", "/de-DE", "/en-US") and urlparse(url).path.rstrip("/"):
        return {"art": "weg", "grund": "Händlerseite leitet auf die Startseite um"}
    text = sichtbarer_text(roh)
    # Sperr- oder Captcha-Seiten (oft mit Status 200) wie „nicht erreichbar“ behandeln, sonst sähe der Artikel verschwunden aus
    if SPERRSEITE.search(text[:3000]) or (len(text) < 1500 and not preise_im_text(text)):
        return {"art": "fehler"}
    tokens = merkmale(eintrag)
    token_da = [n for n, t in enumerate(tokens) if finde(text, t) >= 0]
    auslauf = bool(AUSLAUF.search(text))
    info = {"ausverkauft": bool(AUSVERKAUFT.search(text)), "auslauf_text": auslauf,
            "token": basis["token"] if "token" in basis else (token_da[0] if token_da else None)}

    # Ausgelaufen nur, wenn sich gegenüber dem ersten Lauf etwas geändert hat
    grund = None
    if basis.get("token") is not None and basis["token"] not in token_da:
        grund = "Artikelnummer steht nicht mehr auf der Händlerseite"
    elif "auslauf_text" in basis and auslauf and not basis["auslauf_text"]:
        grund = "Händlerseite meldet jetzt „nicht mehr lieferbar“ o. ä."
    if grund:
        return {"art": "auslauf", "grund": grund, **info}

    k = kandidaten(roh, text, tokens)
    leseweg = basis.get("weg")
    if leseweg:
        wert = k.get(leseweg)
        if wert is None:
            return {"art": "unlesbar", **info}
        return {"art": "ok", "ek": round(wert / MWST, 2) if basis.get("brutto") else wert, **info}

    # Einmessen: welcher Leseweg findet den bekannten EK wieder? Artikelnummer-nahe Preise zuerst.
    for name in sorted(k, key=lambda n: (not n.startswith("nach:"), n)):
        brutto = passt(k[name], eintrag.get("ek_netto"))
        if brutto is not None:
            return {"art": "eingemessen", "weg": name, "brutto": brutto,
                    "ek": round(k[name] / MWST, 2) if brutto else k[name], **info}
    return {"art": "nicht_pruefbar", **info}


# ---------------------------------------------------------------- Dateien

def lade_csv(pfad):
    if not pfad.exists():
        return []
    with pfad.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def schreibe_csv(pfad, kopf, zeilen):
    with pfad.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(kopf)
        w.writerows(zeilen)


def euro(x):
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " EUR"


# ---------------------------------------------------------------- Ablauf

def main(argv):
    nur_melden = "--nur-melden" in argv
    ohne_bremse = "--ohne-bremse" in argv  # von Hand nach Prüfung des Berichts
    pfad = next((a for a in argv if not a.startswith("--")), os.environ.get("BEZUGSQUELLEN_DATEI"))
    bezug = json.loads(Path(pfad).read_text(encoding="utf-8"))
    vk = {r["sku"]: float(r["preis_netto"]) for r in lade_csv(PREISE)}
    aus = {r["sku"]: r for r in lade_csv(AUSGEBLENDET)}
    stand = json.loads(STAND.read_text(encoding="utf-8")) if STAND.exists() else {}
    erster_lauf = not stand
    if erster_lauf:
        nur_melden = True
    heute = date.today().isoformat()
    stand.setdefault("artikel", {})

    zu_pruefen = {s: e for s, e in bezug.items() if e.get("bestell_url") and (s in vk or s in aus)}
    nach_url = {}
    for s, e in zu_pruefen.items():
        nach_url.setdefault(e["bestell_url"], []).append(s)

    ergebnisse, erreichbar = {}, 0
    for url, skus in sorted(nach_url.items()):
        status, final, roh = lesen(url)
        erreichbar += status == 200
        for s in skus:
            ergebnisse[s] = pruefe(zu_pruefen[s], status, final, roh, stand["artikel"].get(s, {}))
        time.sleep(PAUSE)

    preis_neu, preis_gross, ausblenden, verdacht, zurueck, ausverkauft, unlesbar, nicht_pruefbar, fehler = ([] for _ in range(9))
    for s, r in sorted(ergebnisse.items()):
        a = stand["artikel"].setdefault(s, {})
        art = r["art"]
        if art == "fehler":
            fehler.append(s)
            continue
        if "auslauf_text" not in a and "token" in r:  # Ausgangslage beim ersten Sehen merken
            a.update({"token": r["token"], "auslauf_text": r["auslauf_text"], "seit": heute})
        if r.get("ausverkauft"):
            ausverkauft.append(s)
        if art in ("weg", "auslauf"):
            if s not in aus:
                (ausblenden if a.get("verdacht") else verdacht).append((s, r["grund"]))
                a.setdefault("verdacht", heute)
            continue
        a.pop("verdacht", None)
        if art == "eingemessen":
            a.update({"weg": r["weg"], "brutto": r["brutto"]})
            a.pop("nicht_pruefbar", None)
            art = "ok"
        if art == "nicht_pruefbar":
            if not a.get("nicht_pruefbar"):
                nicht_pruefbar.append(s)
            a["nicht_pruefbar"] = True
            continue
        if art == "unlesbar":
            unlesbar.append(s)
            continue
        neu = round(r["ek"] * AUFSCHLAG, 2)
        if s in aus:
            zurueck.append((s, neu))
            continue
        alt = vk.get(s)
        if alt is not None and abs(neu - alt) >= 0.01:
            (preis_gross if abs(neu - alt) / alt > MAX_SPRUNG else preis_neu).append((s, alt, neu, r["ek"]))

    geprueft = len(nach_url)
    bremse = []
    if geprueft and erreichbar / geprueft < MIN_ERREICHBAR:
        bremse.append(f"nur {erreichbar} von {geprueft} Händlerseiten erreichbar")
    if len(ausblenden) > MAX_AUSBLENDEN:
        bremse.append(f"{len(ausblenden)} Artikel wären auf einmal auszublenden")
    if len(preis_neu) > MAX_PREISAENDERUNGEN:
        bremse.append(f"{len(preis_neu)} Preisänderungen auf einmal")
    if ohne_bremse:
        bremse = []
    aendern = not nur_melden and not bremse

    if aendern:
        for s, alt, neu, _ in preis_neu:
            vk[s] = neu
        for s, grund in ausblenden:
            aus[s] = {"sku": s, "preis_netto": f"{vk.pop(s):.2f}", "seit": heute, "grund": grund}
        for s, neu in zurueck:
            vk[s] = neu
            aus.pop(s)
        schreibe_csv(PREISE, ["sku", "preis_netto"], [[s, f"{p:.2f}"] for s, p in sorted(vk.items())])
        schreibe_csv(AUSGEBLENDET, ["sku", "preis_netto", "seit", "grund"],
                     [[r["sku"], r["preis_netto"], r["seit"], r["grund"]] for _, r in sorted(aus.items())])
    STAND.write_text(json.dumps(stand, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    # ------------------------------------------------ Bericht (nur für die Mail)
    def zeile(s):
        e = zu_pruefen[s]
        ausf = f" ({e['preis_bezug']})" if e.get("preis_bezug") else ""
        return (f"{s}  {e.get('hersteller', '')} {e.get('artikel', '')}{ausf}".strip() +
                f"\n    {e.get('bezugsquelle', '')}: {e['bestell_url']}")

    teile = []
    if erster_lauf:
        teile.append("ERSTER LAUF: Der Wächter hat sich eingemessen und noch nichts im Shop geändert. "
                     "Ab dem nächsten Lauf passt er Preise an und blendet ausgelaufene Artikel aus.")
    elif nur_melden:
        teile.append("PROBELAUF: Es wurde nichts im Shop geändert.")
    if bremse:
        teile.append("SICHERHEITSBREMSE: Nichts geändert, weil " + " und ".join(bremse) +
                     ". Bitte kurz ansehen; wenn alles stimmt, den Wächter in GitHub von Hand starten "
                     "(Actions > Preiswächter > Run workflow, Haken bei „Sicherheitsbremse übergehen“).")
    tun = "geändert" if aendern else "würde geändert"
    if preis_neu:
        teile.append(f"PREISE {tun.upper()} ({len(preis_neu)}), Verkaufspreis = neuer Einkaufspreis + 10 %:\n" + "\n".join(
            f"- {zeile(s)}\n    EK jetzt {euro(ek)}, Verkauf {euro(alt)} -> {euro(neu)}" for s, alt, neu, ek in preis_neu))
    if preis_gross:
        teile.append(f"GROSSER PREISSPRUNG, NICHT übernommen, bitte prüfen ({len(preis_gross)}):\n" + "\n".join(
            f"- {zeile(s)}\n    gelesen EK {euro(ek)}, Verkauf wäre {euro(alt)} -> {euro(neu)}" for s, alt, neu, ek in preis_gross))
    if ausblenden:
        teile.append(f"AUSGEBLENDET{'' if aendern else ' (vorgeschlagen)'} ({len(ausblenden)}), zweimal hintereinander nicht verfügbar:\n" +
                     "\n".join(f"- {zeile(s)}\n    {g}" for s, g in ausblenden))
    if zurueck:
        teile.append(f"WIEDER DA{'' if aendern else ' (vorgeschlagen)'} ({len(zurueck)}), wieder eingeblendet:\n" +
                     "\n".join(f"- {zeile(s)}\n    Verkauf {euro(n)}" for s, n in zurueck))
    if verdacht:
        teile.append(f"VERDACHT, wird morgen nochmal geprüft ({len(verdacht)}):\n" + "\n".join(f"- {zeile(s)}\n    {g}" for s, g in verdacht))
    if nicht_pruefbar:
        teile.append(f"NICHT AUTOMATISCH PRÜFBAR ({len(nicht_pruefbar)}), Preis auf der Seite nicht eindeutig lesbar "
                     "(wird nur einmal gemeldet; Seite weg oder Artikel ausgelaufen erkennt der Wächter trotzdem):\n" +
                     "\n".join(f"- {zeile(s)}" for s in nicht_pruefbar))
    if unlesbar:
        teile.append(f"Heute nicht lesbar ({len(unlesbar)}), Seite hat sich evtl. umgebaut:\n" + "\n".join(f"- {zeile(s)}" for s in unlesbar))
    hosts = {}
    for s in fehler:
        hosts[zu_pruefen[s].get("bezugsquelle") or urlparse(zu_pruefen[s]["bestell_url"]).netloc] = hosts.get(
            zu_pruefen[s].get("bezugsquelle") or urlparse(zu_pruefen[s]["bestell_url"]).netloc, 0) + 1
    if hosts:
        teile.append("Nicht erreichbar (keine Änderung, nur zur Info):\n" + "\n".join(f"- {h}: {n} Artikel" for h, n in sorted(hosts.items())))
    if ausverkauft:
        teile.append(f"Zur Info: bei {len(ausverkauft)} Artikeln steht auf der Händlerseite „ausverkauft“ o. ä. "
                     "(oft nur vorübergehend, wird nicht ausgeblendet).")

    wichtig = bool(preis_neu or preis_gross or ausblenden or zurueck or bremse or erster_lauf or nicht_pruefbar)
    kopf = (f"Preiswächter {heute}: {geprueft} Händlerseiten geprüft, {erreichbar} erreichbar, "
            f"{len(ergebnisse)} Artikel.")
    bericht = kopf + "\n\n" + ("\n\n".join(teile) if teile else "Alles unverändert.") + "\n"
    (ROOT / "bericht.txt").write_text(bericht, encoding="utf-8")
    teile_betreff = [f"{n} {name}" for n, name in ((len(preis_neu), "Preise"), (len(ausblenden), "ausgeblendet"),
                                                   (len(preis_gross), "zu pruefen"), (len(zurueck), "wieder da")) if n]
    if bremse:
        teile_betreff.insert(0, "Sicherheitsbremse")
    if erster_lauf:
        teile_betreff.insert(0, "erster Lauf")
    (ROOT / "betreff.txt").write_text(f"Preiswaechter {date.today():%d.%m.}: " + (", ".join(teile_betreff) or "alles ruhig"),
                                      encoding="utf-8")

    # Öffentliches Log: nur Zahlen
    print(f"Seiten {geprueft}, erreichbar {erreichbar}, Artikel {len(ergebnisse)}; Preisänderungen {len(preis_neu)}, "
          f"große Sprünge {len(preis_gross)}, ausgeblendet {len(ausblenden)}, Verdacht {len(verdacht)}, wieder da {len(zurueck)}, "
          f"nicht prüfbar {sum(1 for a in stand['artikel'].values() if a.get('nicht_pruefbar'))}, "
          f"geändert: {'ja' if aendern and (preis_neu or ausblenden or zurueck) else 'nein'}")
    ausgabe = os.environ.get("GITHUB_OUTPUT")
    if ausgabe:
        with open(ausgabe, "a") as f:
            f.write(f"wichtig={'ja' if wichtig else 'nein'}\n")
            f.write(f"geaendert={'ja' if aendern and (preis_neu or ausblenden or zurueck) else 'nein'}\n")


if __name__ == "__main__":
    main(sys.argv[1:])
