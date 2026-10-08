"""Einfache technische Prinzipskizzen (SVG) aus den Produktmerkmalen.

Eigene Zeichnungen statt Herstellerbildern: Form nach Bauform, beschriftet mit Gewinde, Teller- bzw.
Rohrmaß und Traglast. Nicht maßstäblich; verbindlich bleibt das Datenblatt.
"""
import html
import re

NAVY, GRUEN, GRAU, HELL = "#1b2836", "#4fa82e", "#8b939b", "#e8ecef"


def _zahl(text):
    m = re.search(r"\d+(?:[.,]\d+)?", text or "")
    return float(m.group().replace(",", ".")) if m else None


def _gewinde(liste):
    if not liste:
        return ""
    m = [g for g in liste if g.startswith("M")]
    if len(m) > 2:
        return f"{m[0]} – {m[-1]}"
    return " / ".join(liste[:2])


def _mass(text):
    t = re.sub(r"\s*mm$", "", (text or "").strip())
    t = re.sub(r"^(Teller|Ø)\s*", "", t, flags=re.I)
    return f"Ø {t} mm" if t else ""


def _txt(x, y, text, anker="middle", gross=13, farbe=NAVY, fett=False):
    gewicht = ' font-weight="700"' if fett else ""
    return (f'<text x="{x}" y="{y}" text-anchor="{anker}" font-size="{gross}" fill="{farbe}"{gewicht}>'
            f'{html.escape(text)}</text>')


def _masslinie(x1, x2, y, text):
    if not text:
        return ""
    return (f'<path d="M{x1} {y}H{x2}M{x1} {y - 5}v10M{x2} {y - 5}v10" stroke="{GRAU}" stroke-width="1.2" fill="none"/>'
            + _txt((x1 + x2) / 2, y + 17, text))


def _gewindestange(x, y1, y2, breite=14):
    gaenge = "".join(f'<path d="M{x - breite / 2} {y} l{breite} 5" stroke="{GRAU}" stroke-width="1"/>'
                     for y in range(int(y1) + 4, int(y2) - 4, 7))
    return (f'<rect x="{x - breite / 2}" y="{y1}" width="{breite}" height="{y2 - y1}" fill="{HELL}" stroke="{NAVY}" stroke-width="1.6"/>'
            + gaenge)


def _stellfuss(gew, mass, d, gelenk):
    w = 70 + min(d or 60, 160) * 0.8          # Tellerbreite wächst mit dem Durchmesser
    x0, x1 = 160 - w / 2, 160 + w / 2
    teile = [_gewindestange(160, 30, 150)]
    teile.append(f'<path d="M148 118h24l4 8h-32z" fill="{NAVY}"/>')  # Mutter
    if gelenk:
        teile.append(f'<circle cx="160" cy="152" r="11" fill="{HELL}" stroke="{NAVY}" stroke-width="1.6"/>')
    teile.append(f'<path d="M{x0 + 10} 160 Q160 146 {x1 - 10} 160 L{x1} 172 H{x0} Z" fill="{HELL}" stroke="{NAVY}" stroke-width="1.6"/>')
    teile.append(f'<rect x="{x0}" y="172" width="{w}" height="6" fill="{GRUEN}"/>')  # Sohle
    if gew:
        teile.append(f'<path d="M170 60h40" stroke="{GRAU}" stroke-width="1"/>' + _txt(214, 64, gew, "start", 14, NAVY, True))
    teile.append(_masslinie(x0, x1, 196, mass))
    return teile


def _stellbein(gew, mass, d):
    teile = [f'<rect x="146" y="14" width="28" height="104" fill="{HELL}" stroke="{NAVY}" stroke-width="1.6"/>',
             _gewindestange(160, 118, 156, 12),
             f'<path d="M136 158h48l6 14h-60z" fill="{HELL}" stroke="{NAVY}" stroke-width="1.6"/>',
             f'<rect x="130" y="172" width="60" height="5" fill="{GRUEN}"/>']
    if gew:
        teile.append(f'<path d="M170 136h40" stroke="{GRAU}" stroke-width="1"/>' + _txt(214, 140, gew, "start", 14, NAVY, True))
    teile.append(_masslinie(130, 190, 196, mass))
    return teile


def _einschlag(gew, rohr):
    teile = [f'<path d="M110 40V120M210 40V120" stroke="{NAVY}" stroke-width="5"/>',
             f'<rect x="114" y="80" width="92" height="40" fill="{GRUEN}" opacity=".25"/>',
             "".join(f'<path d="M114 {y}l-6 4M206 {y}l6 4" stroke="{NAVY}" stroke-width="1.6"/>' for y in (86, 96, 106)),
             f'<rect x="100" y="120" width="120" height="8" fill="{HELL}" stroke="{NAVY}" stroke-width="1.6"/>',
             _gewindestange(160, 128, 166, 12),
             f'<path d="M136 166h48l6 10h-60z" fill="{HELL}" stroke="{NAVY}" stroke-width="1.6"/>']
    if rohr:
        teile.append(_txt(160, 26, rohr, "middle", 14, NAVY, True))
    if gew:
        teile.append(f'<path d="M170 148h40" stroke="{GRAU}" stroke-width="1"/>' + _txt(214, 152, gew, "start", 14, NAVY, True))
    return teile


def _daempfer(gew, mass, d):
    return [_gewindestange(160, 26, 70, 12),
            f'<rect x="96" y="70" width="128" height="10" fill="{HELL}" stroke="{NAVY}" stroke-width="1.6"/>',
            f'<path d="M104 80 Q96 115 104 150 H216 Q224 115 216 80 Z" fill="{GRAU}" opacity=".45" stroke="{NAVY}" stroke-width="1.6"/>',
            f'<rect x="96" y="150" width="128" height="10" fill="{HELL}" stroke="{NAVY}" stroke-width="1.6"/>',
            _gewindestange(160, 160, 182, 12),
            (f'<path d="M168 44h42" stroke="{GRAU}" stroke-width="1"/>' + _txt(214, 48, gew, "start", 14, NAVY, True)) if gew else "",
            _masslinie(96, 224, 200, mass)]


def _rolle(mass):
    return [f'<rect x="130" y="20" width="60" height="10" fill="{HELL}" stroke="{NAVY}" stroke-width="1.6"/>',
            f'<path d="M140 30v60M180 30v60" stroke="{NAVY}" stroke-width="5"/>',
            f'<circle cx="160" cy="120" r="52" fill="{HELL}" stroke="{NAVY}" stroke-width="1.6"/>',
            f'<circle cx="160" cy="120" r="34" fill="none" stroke="{GRAU}" stroke-width="1.2"/>',
            f'<circle cx="160" cy="120" r="6" fill="{NAVY}"/>',
            _masslinie(108, 212, 194, mass)]


def zeichnung(p, klein=False):
    m = p["merkmale"]
    bauform = (m.get("Bauform") or [""])[0]
    gew = _gewinde(m.get("Gewinde") or [])
    mass = _mass(m.get("Durchmesser", ""))
    d = _zahl(m.get("Durchmesser", ""))
    rohr = " / ".join((m.get("Rohrmaß") or [])[:2])
    if bauform in ("Einschlagfuß", "Gewindeeinsatz"):
        teile = _einschlag(gew, rohr)
    elif bauform == "Schwingungsdämpfer":
        teile = _daempfer(gew, mass, d)
    elif bauform == "Spezialausführung" or "rollen-sonderloesungen" in p["kategorien"]:
        teile = _rolle(mass)
    elif bauform == "Stellbein":
        teile = _stellbein(gew, mass, d)
    else:
        teile = _stellfuss(gew, mass, d, bauform == "Gelenkfuß")
    fuss = "" if klein else _txt(312, 234, "Prinzipskizze, nicht maßstäblich", "end", 10, GRAU)
    titel = html.escape(f"Prinzipskizze {p['name']}")
    return (f'<svg class="bf-skizze" viewBox="0 0 320 240" role="img" aria-label="{titel}" xmlns="http://www.w3.org/2000/svg" '
            f'font-family="-apple-system,Segoe UI,Roboto,Arial,sans-serif">'
            f'<rect width="320" height="240" fill="#fff"/>{"".join(teile)}{fuss}</svg>')
