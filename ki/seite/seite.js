/* beinundfuß.de: Kopfleiste, Einblenden, Akkordeon, Lastrechner, Kontakt-Coupon. */
(function () {
  "use strict";
  var ruhig = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var kopf = document.querySelector(".bf-kopf");
  var kapitel = [].slice.call(document.querySelectorAll("main [data-feld], footer[data-feld]"));

  // Kopfleiste nimmt die Farbe des Abschnitts an, der gerade unter ihr liegt
  function kopfFarbe() {
    var linie = kopf.offsetHeight / 2;
    for (var i = kapitel.length - 1; i >= 0; i--) {
      if (kapitel[i].getBoundingClientRect().top <= linie) {
        var f = kapitel[i].getAttribute("data-feld");
        if (kopf.getAttribute("data-feld") !== f) kopf.setAttribute("data-feld", f);
        return;
      }
    }
  }

  // Bild im Hero bewegt sich beim Scrollen leicht mit
  var bild = document.querySelector(".kb-hero-bild");
  function drift() {
    if (!bild || ruhig || window.innerWidth < 761) return;
    var y = Math.min(window.scrollY, window.innerHeight);
    bild.style.translate = "0 " + (y * -0.06).toFixed(1) + "px";
  }
  var geplant = false;
  window.addEventListener("scroll", function () {
    if (geplant) return;
    geplant = true;
    requestAnimationFrame(function () { geplant = false; kopfFarbe(); drift(); });
  }, { passive: true });
  kopfFarbe();

  // Teile jedes Abschnitts erscheinen nacheinander
  var rein = [].slice.call(document.querySelectorAll("[data-rein]"));
  kapitel.forEach(function (k) {
    [].slice.call(k.querySelectorAll("[data-rein]")).forEach(function (el, i) { el.style.setProperty("--v", (i * 80) + "ms"); });
  });
  if ("IntersectionObserver" in window) {
    var beob = new IntersectionObserver(function (eintraege) {
      eintraege.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("ist-da"); beob.unobserve(e.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px" });
    rein.forEach(function (el) { beob.observe(el); });
  } else {
    rein.forEach(function (el) { el.classList.add("ist-da"); });
  }

  // Akkordeon der Einsätze: ein Feld ist immer offen
  var panels = [].slice.call(document.querySelectorAll(".kb-akk-panel"));
  panels.forEach(function (p) {
    p.querySelector(".kb-akk-kopf").addEventListener("click", function () {
      panels.forEach(function (q) {
        var offen = q === p;
        q.classList.toggle("ist-offen", offen);
        q.querySelector(".kb-akk-kopf").setAttribute("aria-expanded", offen ? "true" : "false");
      });
      var knopf = p.querySelector(".kb-anw");
      if (knopf) knopf.focus({ preventScroll: true });
    });
  });

  // Lastrechner: Gewicht und Anzahl Füße ergeben die Last pro Fuß in Newton
  var kg = document.getElementById("kb-kg");
  var anz = document.getElementById("kb-anzahl");
  var aus = document.getElementById("kb-last");
  var notiz = document.getElementById("kb-last-notiz");
  var frage = document.getElementById("kb-last-frage");
  function zahl(x) { return Math.round(x).toString().replace(/\B(?=(\d{3})+$)/g, "."); }
  function rechnen() {
    var g = parseFloat(kg.value), n = parseInt(anz.value, 10);
    if (!(g > 0) || !(n > 0)) { aus.textContent = "–"; return; }
    var tragend = n >= 4 ? n - 1 : n;
    var newton = Math.ceil(g * 9.81 / tragend / 10) * 10;
    aus.textContent = zahl(newton) + " N";
    notiz.textContent = n >= 4
      ? "pro Fuß, gerechnet mit " + tragend + " tragenden Füßen, weil auf unebenem Boden oft einer kaum Last trägt."
      : "pro Fuß, bei " + n + (n === 1 ? " Fuß." : " Füßen.");
    frage.setAttribute("data-frage", "Mein Gerät wiegt " + zahl(g) + " kg und steht auf " + n + (n === 1 ? " Fuß" : " Füßen") +
      ", also etwa " + zahl(newton) + " N pro Fuß. Welche Füße passen?");
    if (!ruhig) { aus.classList.remove("ist-neu"); void aus.offsetWidth; aus.classList.add("ist-neu"); setTimeout(function () { aus.classList.remove("ist-neu"); }, 260); }
  }
  if (kg && anz) {
    kg.addEventListener("input", rechnen);
    anz.addEventListener("input", rechnen);
    document.getElementById("kb-rechner").addEventListener("submit", function (ev) { ev.preventDefault(); frage.click(); });
    rechnen();
  }

  // Kontakt-Coupon: baut eine lesbare E-Mail statt des rohen Formularformats
  var coupon = document.getElementById("kb-coupon");
  if (coupon) coupon.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var d = new FormData(coupon);
    var text = (d.get("Nachricht") || "") + "\n\n" + (d.get("Name") || "") + "\n" + (d.get("E-Mail") || "") +
      (d.get("Telefon") ? "\nTelefon: " + d.get("Telefon") : "");
    var ziel = coupon.getAttribute("action").replace(/^mailto:/, "");
    window.location.href = "mailto:" + ziel + "?subject=" + encodeURIComponent("Anfrage über beinundfuß.de") + "&body=" + encodeURIComponent(text);
  });
})();
