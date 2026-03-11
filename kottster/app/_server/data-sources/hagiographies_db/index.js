import { KnexBetterSqlite3Adapter } from "@kottster/server";
import knex from "knex";

/**
 * Replace the following with your connection options.
 * Learn more at https://knexjs.org/guide/#configuration-options
 */
const client = knex({
  client: "better-sqlite3",
  connection: {
    filename: process.env.DB_PATH || "/data/hagiographies.db",
  },
  useNullAsDefault: true,
  pool: {
    afterCreate: (conn, done) => {
      conn.pragma("journal_mode = DELETE");
      conn.pragma("locking_mode = EXCLUSIVE");
      conn.pragma("busy_timeout = 5000");
      done(null, conn);
    },
  },
});

export default new KnexBetterSqlite3Adapter(client);
