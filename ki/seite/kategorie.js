// Kategorieseiten: Modelle sortieren (Preis, Gewinde, Größe) und nach Material, Gewinde oder Rohrmaß filtern.
// Ohne JavaScript bleibt die Liste nach Preis sortiert und die Leiste unsichtbar.
(() => {
  const liste = document.getElementById("pr-modelle");
  const leiste = document.querySelector(".pr-werkzeug");
  if (!liste || !leiste) return;
  const eintraege = [...liste.children];
  const sortierung = document.getElementById("pr-sortierung");
  const anzahl = document.getElementById("pr-anzahl");
  const leer = document.getElementById("pr-leer");
  const zurueck = document.getElementById("pr-zuruecksetzen");
  const gruppen = [...leiste.querySelectorAll(".pr-filter-gruppe")];
  leiste.hidden = false;

  const zahl = (li, k) => parseFloat(li.dataset[k]);
  const vergleich = {
    preis: (a, b) => zahl(a, "preis") - zahl(b, "preis"),
    "preis-ab": (a, b) => zahl(b, "preis") - zahl(a, "preis"),
    gewinde: (a, b) => zahl(a, "gewinde") - zahl(b, "gewinde") || zahl(a, "groesse") - zahl(b, "groesse") || zahl(a, "preis") - zahl(b, "preis"),
    groesse: (a, b) => zahl(a, "groesse") - zahl(b, "groesse") || zahl(a, "gewinde") - zahl(b, "gewinde") || zahl(a, "preis") - zahl(b, "preis"),
  };

  function anwenden() {
    // Innerhalb einer Gruppe reicht ein gewählter Wert (oder), zwischen den Gruppen müssen alle passen (und)
    const aktiv = gruppen.map((g) => ({
      merkmal: g.dataset.merkmal,
      werte: [...g.querySelectorAll('[aria-pressed="true"]')].map((k) => k.dataset.wert),
    })).filter((g) => g.werte.length);
    let sichtbar = 0;
    for (const li of eintraege) {
      const passt = aktiv.every((g) => (li.dataset[g.merkmal] || "").split("|").some((w) => g.werte.includes(w)));
      li.hidden = !passt;
      if (passt) sichtbar++;
    }
    eintraege.sort(vergleich[sortierung.value] || vergleich.preis).forEach((li) => liste.appendChild(li));
    anzahl.textContent = sichtbar;
    leer.hidden = sichtbar > 0;
    zurueck.hidden = !aktiv.length;
  }

  sortierung.addEventListener("change", anwenden);
  leiste.addEventListener("click", (ev) => {
    const k = ev.target.closest("[data-wert]");
    if (!k) return;
    k.setAttribute("aria-pressed", k.getAttribute("aria-pressed") === "true" ? "false" : "true");
    anwenden();
  });
  zurueck.addEventListener("click", () => {
    leiste.querySelectorAll('[aria-pressed="true"]').forEach((k) => k.setAttribute("aria-pressed", "false"));
    anwenden();
  });
})();
