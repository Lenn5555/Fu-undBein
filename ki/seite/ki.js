/* KI-Berater von beinundfuß.de: Chat, Produktkarten mit Preis, Bestellformular. */
(function () {
  "use strict";
  var cfg = window.bfKi || {};
  var box = document.getElementById("ki");
  var form = document.getElementById("ki-eingabe");
  var feld = document.getElementById("ki-text");
  var dialog = document.getElementById("ki-bestellen");
  var chips = document.getElementById("ki-chips");
  var verlauf = [];
  var karten = {};

  function el(tag, klasse, text) {
    var n = document.createElement(tag);
    if (klasse) n.className = klasse;
    if (text != null) n.textContent = text;
    return n;
  }
  function euro(x) {
    return x.toFixed(2).replace(".", ",").replace(/\B(?=(\d{3})+,)/g, ".") + " €";
  }
  function bildUrl(b) {
    return b && b.charAt(0) === "/" && b.charAt(1) !== "/" ? (cfg.basis || "") + b : b;
  }
  function preisText(p) {
    var w = p.varianten.length ? p.varianten.map(function (v) { return v.preis; }) : [p.preis];
    var min = Math.min.apply(null, w);
    var ab = p.preis_ab || w.some(function (x) { return x !== min; });
    return (ab ? "ab " : "") + euro(min) + " zzgl. MwSt.";
  }
  function speichern() {
    try { sessionStorage.setItem("bf-ki", JSON.stringify({ verlauf: verlauf, karten: karten })); } catch (e) { /* egal */ }
  }
  function nachUnten() { box.scrollTop = box.scrollHeight; }

  function blase(rolle, text) {
    var b = el("div", "ki-blase ki-" + rolle);
    text.split(/\n{2,}/).forEach(function (abs) { b.appendChild(el("p", null, abs)); });
    box.appendChild(b);
    nachUnten();
    return b;
  }

  function karte(p) {
    var k = el("article", "ki-karte");
    var img = el("img");
    img.src = bildUrl(p.bild); img.alt = ""; img.loading = "lazy";
    k.appendChild(img);
    var t = el("div", "ki-karte-text");
    t.appendChild(el("h3", null, p.name));
    if (p.kurz) t.appendChild(el("p", "ki-kurz", p.kurz));
    var m = el("ul", "ki-merkmale");
    ["Gewinde", "Rohrmaß", "Durchmesser", "Traglast", "Material", "Verstellbereich"].forEach(function (n) {
      if (p.merkmale[n]) m.appendChild(el("li", null, n + ": " + p.merkmale[n]));
    });
    t.appendChild(m);
    var preis = el("p", "ki-preis", preisText(p));
    var wahl = auswahlFelder(p, function () {
      var v = wahl.variante();
      preis.textContent = v ? euro(v.preis) + " netto pro Stück" : preisText(p);
    });
    if (wahl.feld) t.appendChild(wahl.feld);
    t.appendChild(preis);
    var knopf = el("button", "btn", "Bestellen");
    knopf.type = "button";
    knopf.addEventListener("click", function () { bestellen(p, wahl.werte()); });
    t.appendChild(knopf);
    k.appendChild(t);
    return k;
  }

  // Auswahl zum Anklicken: Ausführungen mit eigenem Preis (Varianten) und wählbare Merkmale wie das Gewinde
  var gruppenNr = 0;
  function auswahlFelder(p, beiAenderung, vorher) {
    vorher = vorher || {};
    var feld = null, gruppen = {}, nr = ++gruppenNr;
    function gruppe(titel, schluessel, eintraege, gewaehlt) {
      if (!feld) feld = el("div", "ki-wahl");
      var fs = el("fieldset", "ki-wahl-gruppe");
      fs.appendChild(el("legend", null, titel + " wählen"));
      var reihe = el("div", "ki-pillen");
      eintraege.forEach(function (x, i) {
        var l = el("label", "ki-pille");
        var r = el("input"); r.type = "radio"; r.name = "w" + nr + "-" + schluessel; r.value = x.wert;
        if (i === 0) r.required = true;
        if (x.wert === gewaehlt) r.checked = true;
        r.addEventListener("change", beiAenderung);
        l.appendChild(r);
        l.appendChild(el("span", null, x.text));
        reihe.appendChild(l);
      });
      fs.appendChild(reihe); feld.appendChild(fs);
      gruppen[schluessel] = fs;
    }
    function wert(schluessel) {
      var fs = gruppen[schluessel], r = fs && fs.querySelector("input:checked");
      return r ? r.value : null;
    }
    if (p.varianten.length > 1 || (p.varianten.length === 1 && p.preis_ab)) {
      gruppe("Ausführung", "variante", p.varianten.map(function (v) { return { wert: v.sku, text: v.ausfuehrung + " · " + euro(v.preis) }; }), vorher.variante);
    }
    Object.keys(p.optionen || {}).forEach(function (m) {
      gruppe(m, "opt-" + m, p.optionen[m].map(function (w) { return { wert: w, text: w }; }), vorher.optionen && vorher.optionen[m]);
    });
    return {
      feld: feld,
      variante: function () {
        var sku = gruppen.variante ? wert("variante") : (p.varianten.length === 1 ? p.varianten[0].sku : null);
        return p.varianten.filter(function (v) { return v.sku === sku; })[0] || null;
      },
      werte: function () {
        var o = {};
        Object.keys(p.optionen || {}).forEach(function (m) { var w = wert("opt-" + m); if (w) o[m] = w; });
        var v = this.variante();
        return { variante: v ? v.sku : null, optionen: o };
      }
    };
  }

  function kartenZeigen(liste) {
    if (!liste.length) return;
    var reihe = el("div", "ki-karten");
    liste.forEach(function (p) { karten[p.sku] = p; reihe.appendChild(karte(p)); });
    box.appendChild(reihe);
    nachUnten();
  }

  function begruessen() {
    blase("berater", "Guten Tag! Wofür brauchen Sie Füße? Nennen Sie mir zum Beispiel Anwendung, Gewinde oder Rohrmaß und ungefähre Last. Wenn Sie unsicher sind, frage ich nach.");
  }

  function senden(text) {
    verlauf.push({ rolle: "kunde", text: text });
    blase("kunde", text);
    if (chips) chips.hidden = true;
    var warte = el("div", "ki-blase ki-berater ki-warte");
    warte.setAttribute("aria-label", "Berater schreibt");
    warte.innerHTML = "<span></span><span></span><span></span>";
    box.appendChild(warte); nachUnten();
    form.querySelector("button").disabled = true;
    if (!cfg.api) {
      warte.remove();
      blase("berater", "Der Berater ist noch nicht verbunden. Schreiben Sie uns gern an " + cfg.email + ".");
      form.querySelector("button").disabled = false;
      return;
    }
    fetch(cfg.api.replace(/\/$/, "") + "/beraten", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ verlauf: verlauf })
    }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (x) {
        warte.remove();
        if (!x.ok) throw new Error(x.d.fehler || "Fehler");
        var notiz = x.d.produkte.length ? "\n\n(Angezeigt: " + x.d.produkte.map(function (p) { return p.sku; }).join(", ") + ")" : "";
        verlauf.push({ rolle: "berater", text: x.d.antwort + notiz, produkte: x.d.produkte.map(function (p) { return p.sku; }) });
        var antwortBlase = blase("berater", x.d.antwort);
        kartenZeigen(x.d.produkte);
        // Antworttext oben im Fenster lassen, damit er nicht hinter den Karten verschwindet
        if (x.d.produkte.length) box.scrollTop = antwortBlase.offsetTop - box.offsetTop - 12;
        speichern();
      })
      .catch(function (err) {
        warte.remove();
        verlauf.pop();
        blase("berater ki-fehler", (err && err.message && err.message !== "Failed to fetch" ? err.message : "Keine Verbindung zum Berater.") +
          " Sie erreichen uns auch per E-Mail an " + cfg.email + ".");
      })
      .then(function () { form.querySelector("button").disabled = false; feld.focus(); });
  }

  // Versandkosten im Bestellformular: Lieferland wählen, „ab …“ unter der Summe, Tabelle nach Gewicht zum Aufklappen.
  // Produktgewichte gibt es noch nicht, deshalb kein genauer Betrag (Lenn, 22.10.2026).
  var versandDaten = null;
  function versandLaden() {
    if (versandDaten) return Promise.resolve(versandDaten);
    return fetch((cfg.basis || "") + "/assets/versandkosten.json")
      .then(function (r) { return r.json(); })
      .then(function (v) { versandDaten = v; return v; });
  }
  function versandFelder() {
    var l = el("label", null, "Lieferland *");
    var wahl = el("select"); wahl.name = "land"; wahl.required = true;
    var de = el("option", null, "Deutschland"); de.value = "Deutschland"; wahl.appendChild(de);
    l.appendChild(wahl);
    var ab = el("p", "ki-versand-ab");
    var d = el("details", "ki-versand");
    d.appendChild(el("summary", null, "Versandkosten nach Gewicht anzeigen"));
    var inhalt = el("div", "ki-versand-inhalt");
    d.appendChild(inhalt);
    function kg(x) { return String(x).replace(".", ",") + " kg"; }
    function tarif(v) {
      if (wahl.value === "Deutschland") return { bis: v.deutschland.bis_kg, preise: v.deutschland.preise };
      var t = v.europa.laender.filter(function (x) { return x.land === wahl.value; })[0];
      return { bis: v.europa.bis_kg, preise: t.preise, luft: t.luftfracht };
    }
    function zeigen() {
      if (!versandDaten) { ab.textContent = "Versand: zzgl., den Betrag nennen wir in der Auftragsbestätigung."; return; }
      var t = tarif(versandDaten);
      ab.textContent = "Versand nach " + wahl.value + ": ab " + euro(t.preise[0]) + " netto pro Paket (bis " + kg(t.bis[0]) +
        "), je nach Gewicht. Den genauen Betrag nennen wir in der Auftragsbestätigung.";
      inhalt.textContent = "";
      var tab = el("table");
      t.bis.forEach(function (g, i) {
        var tr = el("tr");
        tr.appendChild(el("td", null, "bis " + kg(g)));
        tr.appendChild(el("td", "ki-zahl", euro(t.preise[i])));
        tab.appendChild(tr);
      });
      inhalt.appendChild(tab);
      if (t.luft) inhalt.appendChild(el("p", null, "Versand per Luftfracht, berechnet nach Volumengewicht."));
      var a = el("a", null, "Alle Versandkosten und Hinweise");
      a.href = (cfg.basis || "") + "/versandkosten/"; a.target = "_blank";
      var p = el("p"); p.appendChild(a); inhalt.appendChild(p);
    }
    wahl.addEventListener("change", zeigen);
    versandLaden().then(function (v) {
      v.europa.laender.forEach(function (x) { var o = el("option", null, x.land); o.value = x.land; wahl.appendChild(o); });
      zeigen();
    }).catch(zeigen);
    zeigen();
    // USt-IdNr.: Pflicht im EU-Ausland, freiwillig außerhalb der EU, in Deutschland ausgeblendet
    var ust = el("label", null, "USt-IdNr. *");
    var ustFeld = el("input"); ustFeld.type = "text"; ustFeld.name = "ust_id"; ustFeld.maxLength = 20;
    ustFeld.placeholder = "z. B. IT12345678901"; ustFeld.autocomplete = "off";
    ust.appendChild(ustFeld);
    var ausland = el("p", "ki-versand-ab");
    function ustZeigen() {
      var info = versandDaten && versandDaten.europa.laender.filter(function (x) { return x.land === wahl.value; })[0];
      var eu = !info || info.eu;
      var inland = wahl.value === "Deutschland";
      ust.hidden = inland; ausland.hidden = inland;
      ustFeld.required = !inland && eu;
      ust.firstChild.textContent = eu ? "USt-IdNr. *" : "USt-IdNr. oder Steuernummer (falls vorhanden)";
      ausland.textContent = eu
        ? "Lieferung ins EU-Ausland ohne deutsche MwSt. mit Ihrer gültigen USt-IdNr. Die erste Bestellung aus dem Ausland liefern wir gegen Vorkasse."
        : "Lieferung außerhalb der EU: Zoll und Versand stimmen wir vor der Auftragsbestätigung mit Ihnen ab. Die erste Bestellung liefern wir gegen Vorkasse.";
    }
    wahl.addEventListener("change", ustZeigen);
    ustZeigen();
    versandLaden().then(ustZeigen, function () {});
    return { land: l, ab: ab, tabelle: d, ust: ust, ausland: ausland };
  }

  function bestellen(p, vorher) {
    dialog.innerHTML = "";
    var f = el("form", "ki-formular");
    f.appendChild(el("h2", null, "Bestellen"));
    f.appendChild(el("p", "ki-kurz", p.name));
    function zeile(label, name, typ, pflicht, extra) {
      var l = el("label", null, label + (pflicht ? " *" : ""));
      var i = el(typ === "textarea" ? "textarea" : "input");
      if (typ !== "textarea") i.type = typ;
      i.name = name; i.required = !!pflicht;
      if (extra) Object.keys(extra).forEach(function (k) { i[k] = extra[k]; });
      l.appendChild(i); f.appendChild(l);
      return i;
    }
    var wahl = auswahlFelder(p, function () { rechnen(); }, vorher);
    if (wahl.feld) f.appendChild(wahl.feld);
    var menge = zeile("Menge (Stück)", "menge", "number", true, { min: 1, max: 100000, value: 4 });
    var summe = el("p", "ki-preis");
    function rechnen() {
      var v = wahl.variante();
      var st = v ? v.preis : p.preis;
      var n = parseInt(menge.value, 10) || 0;
      summe.textContent = "Summe: " + euro(st * n) + " netto zzgl. MwSt. und Versand" + (p.preis_ab && !v ? " (ab-Preis, den Preis für Ihre Ausführung bestätigen wir)" : "");
    }
    menge.addEventListener("input", rechnen);
    f.appendChild(summe); rechnen();
    var versand = versandFelder();
    f.appendChild(versand.land); f.appendChild(versand.ab); f.appendChild(versand.tabelle);
    f.appendChild(versand.ausland);
    zeile("Firma", "firma", "text");
    zeile("Name", "name", "text", true, { autocomplete: "name" });
    zeile("E-Mail", "email", "email", true, { autocomplete: "email" });
    zeile("Telefon", "telefon", "tel", false, { autocomplete: "tel" });
    f.appendChild(versand.ust);
    zeile("Lieferadresse", "adresse", "textarea", true, { rows: 3 });
    zeile("Hinweis", "hinweis", "textarea", false, { rows: 2 });
    var falle = zeile("Website", "website", "text", false, { tabIndex: -1, autocomplete: "off" });
    falle.parentNode.className = "ki-falle";
    var zl = el("label", "ki-check");
    var z = el("input"); z.type = "checkbox"; z.name = "zustimmung"; z.required = true;
    zl.appendChild(z);
    // Text in einem Element, sonst verteilt das Flex-Layout jedes Textstück auf eine eigene Spalte
    var zt = el("span");
    zt.appendChild(document.createTextNode("Ich bestelle als Unternehmer, nicht als Verbraucher. Es gelten die "));
    var agb = el("a", "", "AGB"); agb.href = (cfg.basis || "") + "/agb/"; agb.target = "_blank";
    zt.appendChild(agb);
    zt.appendChild(document.createTextNode(". Meine Angaben werden zur Bearbeitung der Bestellung verwendet (siehe Datenschutz)."));
    zl.appendChild(zt);
    f.appendChild(zl);
    var meldung = el("p", "ki-meldung");
    f.appendChild(meldung);
    var knoepfe = el("div", "ki-knoepfe");
    var ab = el("button", "btn btn-hell", "Abbrechen"); ab.type = "button";
    ab.addEventListener("click", function () { dialog.close(); });
    var ok = el("button", "btn", "Verbindlich bestellen"); ok.type = "submit";
    knoepfe.appendChild(ab); knoepfe.appendChild(ok); f.appendChild(knoepfe);
    f.appendChild(el("p", "ki-kurz", "Sie erhalten von uns eine Auftragsbestätigung per E-Mail. Erst damit kommt der Vertrag zustande."));

    f.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var d = {};
      new FormData(f).forEach(function (v, k) { if (!/^w\d+-/.test(k)) d[k] = v; });
      var w = wahl.werte();
      if (w.variante) d.variante = w.variante;
      d.optionen = w.optionen;
      d.sku = p.sku; d.menge = parseInt(d.menge, 10); d.zustimmung = z.checked;
      ok.disabled = true; meldung.textContent = "Wird gesendet …";
      if (!cfg.api) { meldung.textContent = "Online-Bestellung ist noch nicht verbunden."; ok.disabled = false; return; }
      fetch(cfg.api.replace(/\/$/, "") + "/bestellen", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(d)
      }).then(function (r) { return r.json().then(function (x) { return { ok: r.ok, x: x }; }); })
        .then(function (r) {
          if (!r.ok) throw new Error(r.x.fehler || "Fehler");
          dialog.close();
          blase("berater", "Danke! Ihre Bestellung " + r.x.bestellnummer + " ist bei uns eingegangen. Wir melden uns mit der Auftragsbestätigung.");
        })
        .catch(function (err) {
          meldung.textContent = (err.message !== "Failed to fetch" ? err.message : "Keine Verbindung.") + " Alternativ per E-Mail an " + cfg.email + ".";
          ok.disabled = false;
        });
    });
    dialog.appendChild(f);
    dialog.showModal();
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var t = feld.value.trim();
    if (!t) return;
    feld.value = "";
    feld.style.height = "";
    senden(t);
  });
  feld.addEventListener("input", function () {
    feld.style.height = "";
    feld.style.height = Math.min(feld.scrollHeight, 160) + "px";
  });
  // Beispielfragen, Einsätze, Preisliste und Lastrechner schicken ihre Frage direkt an den Berater
  document.querySelectorAll("[data-frage]").forEach(function (k) {
    k.addEventListener("click", function () {
      if (form.querySelector("button").disabled) return;
      // Fragen von außerhalb des Gesprächs (Einsätze, Preisliste, Lastrechner): zum Gespräch scrollen
      if (!k.closest(".kb-chat")) document.querySelector(".kb-chat").scrollIntoView({ behavior: "smooth", block: "start" });
      senden(k.getAttribute("data-frage"));
    });
  });
  var neu = document.getElementById("ki-neu");
  if (neu) neu.addEventListener("click", function () {
    verlauf = []; karten = {};
    try { sessionStorage.removeItem("bf-ki"); } catch (e) { /* egal */ }
    box.innerHTML = "";
    if (chips) chips.hidden = false;
    begruessen();
    feld.focus();
  });
  feld.addEventListener("keydown", function (ev) {
    if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); form.requestSubmit(); }
  });

  // Gespräch nach Neuladen der Seite wiederherstellen
  try {
    var alt = JSON.parse(sessionStorage.getItem("bf-ki") || "null");
    if (alt && alt.verlauf && alt.verlauf.length) { verlauf = alt.verlauf; karten = alt.karten || {}; }
  } catch (e) { /* egal */ }
  begruessen();
  if (verlauf.length && chips) chips.hidden = true;
  verlauf.forEach(function (m) {
    blase(m.rolle, m.text.replace(/\n\n\(Angezeigt: [^)]*\)$/, ""));
    if (m.produkte) kartenZeigen(m.produkte.map(function (s) { return karten[s]; }).filter(Boolean));
  });

  // Links von den Produktseiten: ?frage=… startet das Gespräch, ?bestellen=Artikelnummer öffnet das Bestellformular
  var q = new URLSearchParams(location.search);
  if (q.get("frage") || q.get("bestellen")) history.replaceState(null, "", location.pathname + location.hash);
  if (q.get("frage")) senden(q.get("frage").slice(0, 1500));
  if (q.get("bestellen")) {
    fetch((cfg.basis || "") + "/assets/katalog.json")
      .then(function (r) { return r.json(); })
      .then(function (liste) {
        var p = liste.filter(function (x) { return x.sku === q.get("bestellen"); })[0];
        if (!p) return;
        // Auswahl von der Produktseite übernehmen: ?variante=… oder ?opt-Gewinde=…
        var optionen = {};
        Object.keys(p.optionen || {}).forEach(function (m) { if (q.get("opt-" + m)) optionen[m] = q.get("opt-" + m); });
        bestellen(p, { variante: q.get("variante"), optionen: optionen });
      })
      .catch(function () { /* Formular bleibt zu, der Berater ist trotzdem da */ });
  }
})();
