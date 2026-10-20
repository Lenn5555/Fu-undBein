#!/usr/bin/env python3
"""Schickt den Bericht des Preiswächters per Resend an die Bestelladresse.

Aufruf: python3 werkzeuge/preiswaechter_mail.py bericht.txt ["Betreff"]
Umgebung: RESEND_API_KEY, EMPFAENGER, ABSENDER (siehe .github/workflows/preiswaechter.yml)
"""
import html
import json
import os
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path


def mail_html(text):
    # Gleicher schlichter Aufbau wie die Bestellmail, damit Outlook sie anzeigt
    sicher = html.escape(text, quote=False)
    sicher = re.sub(r"(https?://[^\s<]+)", r'<a href="\1">\1</a>', sicher).replace("\n", "<br>\n")
    return ('<!DOCTYPE html><html><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8"></head>'
            '<body style="background:#ffffff;color:#000000"><p style="font-family:Arial,Helvetica,sans-serif;'
            f'font-size:14px;line-height:20px;color:#000000">{sicher}</p></body></html>')


def betreff(pfad):
    """Betreff, den der Wächter neben den Bericht gelegt hat (betreff.txt)."""
    datei = Path(pfad).with_name("betreff.txt")
    return datei.read_text(encoding="utf-8").strip() if datei.exists() else f"Preiswaechter {date.today():%d.%m.}"


def main(argv):
    text = Path(argv[0]).read_text(encoding="utf-8")
    titel = argv[1] if len(argv) > 1 else betreff(argv[0])
    # Nur einfache Zeichen im Betreff: Outlook am Computer zeigt die Mail sonst leer
    titel = titel.translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"}))
    if not os.environ.get("RESEND_API_KEY"):
        raise SystemExit("RESEND_API_KEY fehlt, Mail nicht verschickt")
    daten = {"from": os.environ["ABSENDER"], "to": [os.environ["EMPFAENGER"]], "subject": titel,
             "text": text, "html": mail_html(text)}
    req = urllib.request.Request("https://api.resend.com/emails", data=json.dumps(daten).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
                                          "Content-Type": "application/json", "User-Agent": "beinundfuss-preiswaechter"})
    with urllib.request.urlopen(req, timeout=30) as r:
        print(f"Mail verschickt (HTTP {r.status})")


if __name__ == "__main__":
    main(sys.argv[1:])
