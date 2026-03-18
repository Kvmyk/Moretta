import Keycloak from 'keycloak-js';

const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_URL ?? 'http://localhost:3000/auth',
  realm: import.meta.env.VITE_KEYCLOAK_REALM ?? 'moretta',
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID ?? 'moretta-frontend',
});

export default keycloak;
