/* Statistikseite für Lenn: holt den anonymen Bericht vom Server (nur mit Schlüssel) und zeigt Trichter, Bestellwert, Artikel, Herkunft und Lücken. */
(function () {
  "use strict";
  var cfg = window.bfZaehlen || {};
  var form = document.getElementById("st-form");
  var feld = document.getElementById("st-schluessel");
  var tage = document.getElementById("st-tage");
  var ziel = document.getElementById("st-ergebnis");
  var meldung = document.getElementById("st-meldung");
  try { feld.value = localStorage.getItem("bf-statistik") || ""; } catch (e) { /* egal */ }

  var SCHRITTE = [
    ["besuch", "Besuche"],
    ["produktseite", "Produktseite angesehen"],
    ["chat_start", "Berater gefragt"],
    ["produktkarten", "Berater zeigte Produkte"],
    ["bestellformular", "Bestellformular geöffnet"],
    ["bestellung", "Bestellung abgeschickt"],
  ];
  var QUELLEN = { werbung: "Google-Werbung", google: "Google-Suche", suchmaschine: "Andere Suchmaschine", andere_seite: "Link auf anderer Seite", direkt: "Direkt (Lesezeichen, Mail, eingetippt)" };
  var EINSTIEG = { start: "Startseite", produkt: "Produktseite", kategorie: "Kategorieseite", uebersicht: "Produktübersicht", sonstige: "Sonstige" };

  function el(tag, text, klasse) {
    var n = document.createElement(tag);
    if (text != null) n.textContent = text;
    if (klasse) n.className = klasse;
    return n;
  }
  function zahl(x) { return (x || 0).toLocaleString("de-DE"); }
  function euro(cent) { return ((cent || 0) / 100).toLocaleString("de-DE", { style: "currency", currency: "EUR" }); }
  function quote(a, b) { return b ? Math.round((a || 0) * 1000 / b) / 10 + " %" : "–"; }
  function tabelle(kopf, zeilen) {
    var w = el("div", null, "pr-tabelle"), t = el("table"), th = el("thead"), tr = el("tr"), tb = el("tbody");
    kopf.forEach(function (k, i) { tr.appendChild(el("th", k, i ? "pr-zahl" : null)); });
    th.appendChild(tr); t.appendChild(th);
    zeilen.forEach(function (z) {
      var r = el("tr");
      z.forEach(function (c, i) { r.appendChild(el("td", c, i ? "pr-zahl" : null)); });
      tb.appendChild(r);
    });
    t.appendChild(tb); w.appendChild(t);
    return w;
  }
  function abschnitt(titel, text, inhalt) {
    var s = el("section");
    s.appendChild(el("h2", titel));
    if (text) s.appendChild(el("p", text, "pr-notiz"));
    s.appendChild(inhalt);
    ziel.appendChild(s);
  }
  function sortiert(obj) {
    return Object.keys(obj).sort(function (a, b) { return obj[b] - obj[a]; });
  }

  function zeigen(d) {
    ziel.innerHTML = "";
    var s = d.summe, w = d.werbung;
    abschnitt("Vom Besuch zur Bestellung", "Wie viele Besucher welchen Schritt erreicht haben, in den letzten " + d.tage + " Tagen. Die Quote bezieht sich auf die Besuche.",
      tabelle(["Schritt", "Alle", "Quote", "Davon Werbung", "Quote Werbung"], SCHRITTE.map(function (x) {
        return [x[1], zahl(s[x[0]]), quote(s[x[0]], s.besuch), zahl(w[x[0]]), quote(w[x[0]], w.besuch)];
      })));
    var u = d.umsatz || { netto_cent: 0, werbung_cent: 0, proTag: {} };
    abschnitt("Bestellwert", "Warenwert netto der abgeschickten Bestellungen, ohne Versand und MwSt.",
      tabelle(["", "Alle", "Davon Werbung"], [
        ["Bestellwert netto", euro(u.netto_cent), euro(u.werbung_cent)],
        ["Pro Bestellung", s.bestellung ? euro(u.netto_cent / s.bestellung) : "–", w.bestellung ? euro(u.werbung_cent / w.bestellung) : "–"],
      ]));
    var a = sortiert(d.artikel || {});
    if (a.length) abschnitt("Was bestellt wurde", "Stückzahl je Artikel.",
      tabelle(["Artikel", "Stück"], a.map(function (k) { return [k, zahl(d.artikel[k])]; })));
    var q = sortiert(d.quellen);
    abschnitt("Woher die Besucher kommen", null, q.length
      ? tabelle(["Herkunft", "Besuche", "Anteil"], q.map(function (k) { return [QUELLEN[k] || k, zahl(d.quellen[k]), quote(d.quellen[k], s.besuch)]; }))
      : el("p", "Noch keine Besuche gezählt."));
    var e = sortiert(d.einstieg);
    if (e.length) abschnitt("Wo die Besucher einsteigen", "Viele Einstiege über Produkt- und Kategorieseiten heißen: Google findet die Produkte.",
      tabelle(["Seite", "Besuche"], e.map(function (k) { return [EINSTIEG[k] || k, zahl(d.einstieg[k])]; })));
    var l = sortiert(d.luecken);
    abschnitt("Was gesucht, aber nicht gefunden wurde", "Wenn der Berater nichts Passendes hatte, merkt er sich nur Bauform und Grund, keine Texte und keine Namen.",
      l.length ? tabelle(["Gesucht und warum nicht", "Anzahl"], l.map(function (k) { return [k, zahl(d.luecken[k])]; })) : el("p", "Noch nichts gemeldet."));
    var t = Object.keys(d.proTag).sort().reverse();
    if (t.length) abschnitt("Pro Tag", null, tabelle(["Tag", "Besuche", "Berater", "Bestellformular", "Bestellungen", "Bestellwert"], t.map(function (k) {
      var x = d.proTag[k];
      return [new Date(k + "T12:00:00").toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" }),
        zahl(x.besuch), zahl(x.chat_start), zahl(x.bestellformular), zahl(x.bestellung), euro(u.proTag[k])];
    })));
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var k = feld.value.trim();
    if (!k) return;
    meldung.textContent = "Wird geladen …";
    fetch(cfg.api.replace(/\/$/, "") + "/statistik?tage=" + tage.value, { headers: { Authorization: "Bearer " + k } })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (x) {
        if (!x.ok) throw new Error(x.d.fehler || "Fehler");
        try { localStorage.setItem("bf-statistik", k); } catch (e) { /* egal */ }
        meldung.textContent = "";
        zeigen(x.d);
      })
      .catch(function (err) { meldung.textContent = err.message === "Failed to fetch" ? "Keine Verbindung zum Server." : err.message; });
  });
  if (feld.value) form.requestSubmit();
})();
