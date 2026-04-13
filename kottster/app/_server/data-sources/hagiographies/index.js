import { KnexPgAdapter } from '@kottster/server';
import knex from 'knex';
import { getEnvOrThrow } from '@kottster/common';

const PG_DATABASE_URL = getEnvOrThrow('PG_DATABASE_URL');

/**
 * Learn more at https://knexjs.org/guide/#configuration-options
 */
const client = knex({
  client: 'pg', 
  connection: PG_DATABASE_URL,
  searchPath: ['public']
});

export default new KnexPgAdapter(client);