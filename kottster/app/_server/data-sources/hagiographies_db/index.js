import { KnexBetterSqlite3Adapter } from "@kottster/server";
import knex from "knex";

/**
 * Replace the following with your connection options.
 * Learn more at https://knexjs.org/guide/#configuration-options
 */
const client = knex({
  client: "better-sqlite3",
  connection: {
    filename: "/data/hagiographies.db",
  },
  useNullAsDefault: true,
});

export default new KnexBetterSqlite3Adapter(client);
