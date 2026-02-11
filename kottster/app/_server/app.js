import { createApp, createIdentityProvider } from '@kottster/server';
import schema from '../../kottster-app.json';

/*
 * For security, consider moving the secret data to environment variables.
 * See https://kottster.app/docs/deploying#before-you-deploy
 */
export const app = createApp({
  schema,
  secretKey: 'Tm8qW3xR7vK9pL2nJ5mD4fA6hY1sC0gE',
  kottsterApiToken: 'Rw6xN2kP8mT4vB9sE3yD7fH1jL5qA0cU',

  /*
   * The identity provider configuration.
   * See https://kottster.app/docs/app-configuration/identity-provider
   */
  identityProvider: createIdentityProvider('sqlite', {
    fileName: 'app.db',

    passwordHashAlgorithm: 'bcrypt',
    jwtSecretSalt: 'Qp5kR8mN3xT7wL2v',

    /* The root admin user credentials */
    rootUsername: 'admin',
    rootPassword: 'admin',
  }),
});
