"""Zusätzliche Lesewege für den Preiswächter: echter Browser (für Seiten, die Preise per JavaScript zeigen
oder einfache Abrufe sperren) und Claude als zweiter, unabhängiger Leser des Preises.

Beides ist optional: Fehlt Playwright oder ANTHROPIC_API_KEY, liefern die Funktionen None und der
Wächter meldet den Artikel, statt etwas zu ändern.
"""
import json
import os

MODELL = "claude-opus-5-5"

_browser = None
zaehler = {"browser": 0, "ki": 0}


def browser_lesen(url):
    """Seite mit Chromium laden; (status, final_url, html) oder None, wenn kein Browser verfügbar ist."""
    global _browser
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    zaehler["browser"] += 1
    try:
        if _browser is None:
            pw = sync_playwright().start()
            pfad = os.environ.get("CHROMIUM_PFAD")
            _browser = pw.chromium.launch(executable_path=pfad) if pfad else pw.chromium.launch()
        seite = _browser.new_page(locale="de-DE", user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"))
        try:
            antwort = seite.goto(url, wait_until="domcontentloaded", timeout=45000)
            try:
                seite.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass  # manche Seiten laden ständig nach; der Stand nach 15 s reicht
            return (antwort.status if antwort else 0), seite.url, seite.content()
        finally:
            seite.close()
    except Exception:
        return 0, url, ""


SCHEMA = {
    "type": "object",
    "properties": {
        "gefunden": {"type": "boolean", "description": "true nur, wenn der Preis genau dieses Artikels eindeutig auf der Seite steht"},
        "preis": {"type": "number", "description": "Stückpreis bei Bestellmenge 1, so wie er auf der Seite steht; 0 wenn nicht gefunden"},
        "brutto": {"type": "boolean", "description": "true, wenn der genannte Preis die Mehrwertsteuer enthält"},
        "nicht_mehr_lieferbar": {"type": "boolean", "description": "true nur, wenn die Seite sagt, dass genau dieser Artikel ausgelaufen oder nicht mehr erhältlich ist (nicht bei vorübergehend ausverkauft)"},
    },
    "required": ["gefunden", "preis", "brutto", "nicht_mehr_lieferbar"],
    "additionalProperties": False,
}


def ki_lesen(eintrag, auszug):
    """Claude liest den Stückpreis des Artikels aus dem Seitentext. dict wie SCHEMA oder None."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
    except ImportError:
        return None
    zaehler["ki"] += 1
    artikel = ", ".join(x for x in (eintrag.get("hersteller"), eintrag.get("artikel"), eintrag.get("preis_bezug")) if x)
    frage = (
        "Unten steht der Text einer Händlerseite. Gesucht ist der Preis für genau diesen Artikel bzw. diese Ausführung:\n"
        f"{artikel}\n\n"
        "Nimm den Stückpreis bei Bestellmenge 1 (keine Staffelpreise für größere Mengen, keine Preise anderer Ausführungen, "
        "keine Zubehör- oder Empfehlungsartikel). Wenn Netto- und Bruttopreis dastehen, nimm den Nettopreis. "
        "Wenn du nicht sicher bist, welcher Preis zu genau diesem Artikel gehört, setze gefunden auf false.\n\n"
        f"<seite>\n{auszug}\n</seite>"
    )
    try:
        client = anthropic.Anthropic()
        antwort = client.beta.messages.create(
            model=MODELL,
            max_tokens=4000,
            betas=["server-side-fallback-2026-07-01"],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": frage}],
            extra_body={"fallbacks": "default"},
        )
        if antwort.stop_reason != "end_turn":
            return None
        text = next(b.text for b in antwort.content if b.type == "text")
        daten = json.loads(text)
        brauchbar = (daten.get("gefunden") and daten.get("preis", 0) > 0) or daten.get("nicht_mehr_lieferbar")
        return daten if brauchbar else None
    except Exception as fehler:
        # Nur die Art des Fehlers ins (öffentliche) Log, keine Seiteninhalte
        print(f"KI-Abfrage fehlgeschlagen: {type(fehler).__name__}")
        return None
