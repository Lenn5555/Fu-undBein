// Durable Object mit SQLite: hält die Tagessummen der anonymen Zählung (siehe statistik.js).
import { DurableObject } from "cloudflare:workers";
import { heute } from "./statistik.js";

const AUFBEWAHREN_TAGE = 400;

export class Zaehler extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    ctx.storage.sql.exec(`CREATE TABLE IF NOT EXISTS zahlen (
      tag TEXT NOT NULL, art TEXT NOT NULL, wert TEXT NOT NULL, quelle TEXT NOT NULL, n INTEGER NOT NULL,
      PRIMARY KEY (tag, art, wert, quelle))`);
  }

  zaehlen(eintraege) {
    const tag = heute();
    for (const e of eintraege) {
      this.ctx.storage.sql.exec(
        "INSERT INTO zahlen (tag, art, wert, quelle, n) VALUES (?, ?, ?, ?, ?) ON CONFLICT DO UPDATE SET n = n + excluded.n",
        tag, e.art, e.wert, e.quelle, e.n ?? 1);
    }
  }

  zeilen(tage) {
    const ab = heute(new Date(Date.now() - (tage - 1) * 86400000));
    this.ctx.storage.sql.exec("DELETE FROM zahlen WHERE tag < ?", heute(new Date(Date.now() - AUFBEWAHREN_TAGE * 86400000)));
    return this.ctx.storage.sql.exec("SELECT tag, art, wert, quelle, n FROM zahlen WHERE tag >= ? ORDER BY tag", ab).toArray();
  }
}

export function zaehlerVon(env) {
  return env.ZAEHLER ? env.ZAEHLER.get(env.ZAEHLER.idFromName("alle")) : null;
}
