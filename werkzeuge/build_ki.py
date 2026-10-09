#!/usr/bin/env python3
"""Baut die KI-Version von beinundfuß.de: eine Beraterseite statt Katalog.

Schreibt
  site/                          Beraterseite, Kontakt, Impressum, Datenschutz, Skizzen (GitHub Pages)
  ki/worker/src/katalog.json     alle Produkte MIT Preis, öffentlich unbedenklich (nur Verkaufspreise)
  /mnt/project-files/katalog/intern/ki-bezugsquellen.json
                                 Händler, Bestell-Link und EK je Artikelnummer. NICHT ins Repo,
                                 wird in den Cloudflare-Speicher (KV) des Workers geladen.

Aufruf: python3 werkzeuge/build_ki.py
"""
import csv
import json
import re
import shutil
import sys
from html import escape as e
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site as b  # noqa: E402
from zeichnung import zeichnung  # noqa: E402

ROOT, OUT, CFG = b.ROOT, b.OUT, b.CFG
b.NAV = [("Berater", "/"), ("Kontakt", "/kontakt/")]
INTERN = Path("/mnt/project-files/katalog/intern")
KATALOG = ROOT / "ki/worker/src/katalog.json"


def ohne_html(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def katalog(produkte):
    """Kompakte Liste für den Berater; nur was einen Preis hat."""
    liste = []
    for p in produkte:
        if not b.preise(p):
            continue
        kurz = re.sub(r"\s*Preis und Lieferzeit auf Anfrage\.?", "", p["kurz"]).strip()
        merkmale = {k: (", ".join(v) if isinstance(v, list) else v) for k, v in p["merkmale"].items()}
        liste.append({
            "sku": p["sku"], "name": p["name"], "marke": p["marke"], "kurz": kurz, "merkmale": merkmale,
            "preis": float(p["preis"]) if p["preis"] else None,
            "preis_ab": p["preis_ab"],  # Preis gilt für die günstigste Ausführung der Serie
            "varianten": [{"sku": v["sku"], "ausfuehrung": v["ausfuehrung"], "preis": float(v["preis"])}
                          for v in p["varianten"] if v["preis"]],
            "bild": b.bild_url(p),
        })
    return liste


def bezugsquellen(produkte):
    """Interne Zuordnung Artikelnummer -> Händler; enthält EK, darf nie veröffentlicht werden."""
    eingabe, bezug = {}, {}
    for f in sorted(INTERN.glob("eingabe-*.csv")):
        eingabe.update({r["sku"]: r for r in csv.DictReader(f.open(encoding="utf-8"))})
    for f in sorted(INTERN.glob("bezug-*.csv")):
        bezug.update({r["sku"]: r for r in csv.DictReader(f.open(encoding="utf-8"))})
    daten = {}
    for p in produkte:
        if not b.preise(p):
            continue
        if not p["vergleich"]:
            daten[p["sku"]] = {"bezugsquelle": "TS Systemtechnik, eigenes Sortiment", "hersteller": "TS Systemtechnik"}
            continue
        q, r = bezug.get(p["sku"], {}), eingabe.get(p["sku"], {})
        daten[p["sku"]] = {
            "hersteller": r.get("hersteller", ""), "artikel": r.get("serie_artikel", ""),
            "bezugsquelle": q.get("bezugsquelle", ""), "bestell_url": q.get("bestell_url", ""),
            "ek_netto": float(q["preis_netto_eur"]) if q.get("preis_netto_eur") else None,
            "preis_bezug": q.get("preis_bezug", ""), "notiz": q.get("notiz", ""),
        }
    return daten


def beraterseite():
    api = CFG.get("ki_api", "")
    return b.seite("beinundfuß.de – Ihr Berater für Stellfüße und Einschlagfüße", f"""
<section class="ki-wrap wrap">
<h1>Welchen Fuß brauchen Sie?</h1>
<p class="ki-intro">Beschreiben Sie, wofür der Fuß gedacht ist, oder nennen Sie direkt Gewinde, Rohrmaß und Last.
Unser KI-Berater schlägt passende Produkte mit Preis vor, die Sie gleich bestellen können.</p>
<div id="ki" class="ki" aria-live="polite"></div>
<form id="ki-eingabe" class="ki-eingabe">
<textarea id="ki-text" rows="2" maxlength="1500" placeholder="z. B. Stellfuß M12 für eine Maschine, ca. 300 kg, Boden ist etwas uneben" required></textarea>
<button class="btn" type="submit">Senden</button>
</form>
<p class="ki-hinweis">Sie sprechen mit einer KI. Angaben bitte vor der Bestellung prüfen; verbindlich sind Auftragsbestätigung und Datenblatt.
Ihre Eingaben werden zur Beantwortung an Anthropic übermittelt, siehe <a href="/datenschutz/">Datenschutz</a>.</p>
</section>
<dialog id="ki-bestellen" class="ki-dialog"></dialog>
<script>window.bfKi = {{ api: "{e(api)}", basis: "", email: "{e(CFG['anfrage_email'])}" }};</script>
<script src="/assets/ki.js" defer></script>""", extra_kopf='<link rel="stylesheet" href="/assets/ki.css">')


def main():
    produkte = b.produkte_laden()
    liste = katalog(produkte)
    KATALOG.parent.mkdir(parents=True, exist_ok=True)
    KATALOG.write_text(json.dumps(liste, ensure_ascii=False, indent=0), encoding="utf-8")
    if INTERN.exists():
        ziel = INTERN / "ki-bezugsquellen.json"
        ziel.write_text(json.dumps(bezugsquellen(produkte), ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"intern: {ziel}")

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "assets/skizzen").mkdir(parents=True)
    theme_css = re.sub(r"/\*.*?\*/", "", (b.THEME / "style.css").read_text(encoding="utf-8"), count=1, flags=re.S)
    (OUT / "assets/site.css").write_text(b.CSS + theme_css, encoding="utf-8")
    for datei in ("ki.js", "ki.css"):
        shutil.copy(ROOT / "ki/seite" / datei, OUT / "assets" / datei)
    (OUT / "assets/favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="6" fill="#1b2836"/>'
        '<path d="M16 6v14M12 10h8" stroke="#fff" stroke-width="2.5" fill="none"/><ellipse cx="16" cy="23" rx="8" ry="3" fill="#4fa82e"/></svg>',
        encoding="utf-8")
    for p in produkte:
        if b.preise(p) and not p["bild"]:
            (OUT / "assets/skizzen" / f"{p['slug']}.svg").write_text(zeichnung(p, klein=True), encoding="utf-8")

    def schreibe(pfad, text):
        ziel = OUT / pfad / "index.html" if pfad else OUT / "index.html"
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_text(text, encoding="utf-8")

    schreibe("", beraterseite())
    mail = e(CFG["anfrage_email"])
    schreibe("kontakt", b.textseite("Kontakt", f"<p>Fragen zu Produkten, Sonderanfertigungen oder Mengenpreisen? Schreiben Sie uns.</p>"
                                               f'<p><a class="btn" href="mailto:{mail}">{mail}</a></p>'
                                               f"<p>{e(CFG['betreiber_zeile'])}</p>"))
    for pfad, titel in (("impressum", "Impressum"), ("datenschutz", "Datenschutzerklärung"), ("agb", "Allgemeine Geschäftsbedingungen")):
        datei = b.RECHT / f"{pfad}.html"
        if not datei.exists():
            if pfad == "agb":
                continue
            raise SystemExit(f"Rechtstext fehlt: {datei}")
        schreibe(pfad, b.textseite(titel, datei.read_text(encoding="utf-8")))
    (OUT / "404.html").write_text(b.textseite("Seite nicht gefunden", '<p>Diese Seite gibt es nicht. <a href="/">Zum Berater</a></p>'), encoding="utf-8")
    (OUT / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")

    if b.BASIS:
        for f in OUT.rglob("*.html"):
            t = f.read_text(encoding="utf-8")
            t = re.sub(r'((?:href|src)=")/(?!/)', rf"\1{b.BASIS}/", t)
            f.write_text(t.replace('basis: ""', f'basis: "{b.BASIS}"'), encoding="utf-8")
    if (ROOT / "CNAME").exists():
        shutil.copy(ROOT / "CNAME", OUT / "CNAME")
    print(f"site/: KI-Berater, {len(liste)} Produkte mit Preis im Katalog ({KATALOG.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
