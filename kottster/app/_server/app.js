import { createApp, createIdentityProvider } from '@kottster/server';
import schema from '../../kottster-app.json';
import { getEnvOrThrow } from '@kottster/common'


const KOTTSTER_SECRET_KEY = getEnvOrThrow('KOTTSTER_SECRET_KEY');
const KOTTSTER_JWT_SECRET_SALT = getEnvOrThrow('KOTTSTER_JWT_SECRET_SALT');
const KOTTSTER_API_TOKEN = getEnvOrThrow('KOTTSTER_API_TOKEN');

const KOTTSTER_ROOT_USERNAME = getEnvOrThrow('KOTTSTER_ROOT_USERNAME');
const KOTTSTER_ROOT_USER_PASSWORD = getEnvOrThrow('KOTTSTER_ROOT_USER_PASSWORD');

const KOTTSTER_IDENTITY_DATABASE_PATH = getEnvOrThrow('KOTTSTER_IDENTITY_DATABASE_PATH');

/*
 * For security, consider moving the secret data to environment variables.
 * See https://kottster.app/docs/deploying#before-you-deploy
 */
export const app = createApp({
  schema,
  secretKey: KOTTSTER_SECRET_KEY,
  kottsterApiToken: KOTTSTER_API_TOKEN,

  /*
   * The identity provider configuration.
   * See https://kottster.app/docs/app-configuration/identity-provider
   */
  identityProvider: createIdentityProvider('sqlite', {
    fileName: 'app.db',

    passwordHashAlgorithm: 'bcrypt',
    jwtSecretSalt: KOTTSTER_JWT_SECRET_SALT,

    /* The root admin user credentials */
    rootUsername: KOTTSTER_ROOT_USERNAME,
    rootPassword: KOTTSTER_ROOT_USER_PASSWORD,
  }),
});
