// Durable Object für den Lagerbestand; die Logik steht in lagerkern.js
import { DurableObject } from "cloudflare:workers";
import { LagerKern } from "./lagerkern.js";

export class Lager extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.kern = new LagerKern(ctx.storage.sql, (f) => ctx.storage.transactionSync(f));
  }
  setzen(liste, stand, quelle) { return this.kern.setzen(liste, stand, quelle); }
  alle() { return this.kern.alle(); }
  pruefen(artikel, menge) { return this.kern.pruefen(artikel, menge); }
  abziehen(artikel, menge) { return this.kern.abziehen(artikel, menge); }
  erzwingen(artikel, menge) { return this.kern.erzwingen(artikel, menge); }
  zurueck(artikel, menge) { return this.kern.zurueck(artikel, menge); }
}

export function lagerVon(env) {
  return env.LAGER ? env.LAGER.get(env.LAGER.idFromName("ts")) : null;
}
