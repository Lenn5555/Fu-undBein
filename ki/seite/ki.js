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
    t.appendChild(el("p", "ki-preis", preisText(p)));
    var knopf = el("button", "btn", "Bestellen");
    knopf.type = "button";
    knopf.addEventListener("click", function () { bestellen(p); });
    t.appendChild(knopf);
    k.appendChild(t);
    return k;
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

  function bestellen(p) {
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
    var auswahl = null;
    if (p.varianten.length) {
      var l = el("label", null, "Ausführung *");
      auswahl = el("select"); auswahl.name = "variante"; auswahl.required = true;
      p.varianten.forEach(function (v) {
        var o = el("option", null, v.ausfuehrung + " – " + euro(v.preis)); o.value = v.sku; auswahl.appendChild(o);
      });
      l.appendChild(auswahl); f.appendChild(l);
    }
    var menge = zeile("Menge (Stück)", "menge", "number", true, { min: 1, max: 100000, value: 4 });
    var summe = el("p", "ki-preis");
    function rechnen() {
      var st = auswahl ? p.varianten.filter(function (v) { return v.sku === auswahl.value; })[0].preis : p.preis;
      var n = parseInt(menge.value, 10) || 0;
      summe.textContent = "Summe: " + euro(st * n) + " netto zzgl. MwSt. und Versand" + (p.preis_ab ? " (ab-Preis, Ausführung bestätigen wir)" : "");
    }
    menge.addEventListener("input", rechnen);
    if (auswahl) auswahl.addEventListener("change", rechnen);
    f.appendChild(summe); rechnen();
    zeile("Firma", "firma", "text");
    zeile("Name", "name", "text", true, { autocomplete: "name" });
    zeile("E-Mail", "email", "email", true, { autocomplete: "email" });
    zeile("Telefon", "telefon", "tel", false, { autocomplete: "tel" });
    zeile("Lieferadresse", "adresse", "textarea", true, { rows: 3 });
    zeile("Hinweis", "hinweis", "textarea", false, { rows: 2 });
    var falle = zeile("Website", "website", "text", false, { tabIndex: -1, autocomplete: "off" });
    falle.parentNode.className = "ki-falle";
    var zl = el("label", "ki-check");
    var z = el("input"); z.type = "checkbox"; z.name = "zustimmung"; z.required = true;
    zl.appendChild(z);
    zl.appendChild(document.createTextNode(" Ich bin Gewerbetreibender und stimme zu, dass meine Angaben zur Bearbeitung der Bestellung verwendet werden (siehe Datenschutz)."));
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
      new FormData(f).forEach(function (v, k) { d[k] = v; });
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
  // Beispielfragen und Anwendungskacheln schicken ihre Frage direkt an den Berater
  document.querySelectorAll("[data-frage]").forEach(function (k) {
    k.addEventListener("click", function () {
      if (form.querySelector("button").disabled) return;
      if (k.classList.contains("kb-anw")) form.scrollIntoView({ behavior: "smooth", block: "center" });
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
})();
