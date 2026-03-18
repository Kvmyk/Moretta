import keycloak from './keycloak';

export async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  if (keycloak.authenticated) {
    try {
      await keycloak.updateToken(30);
    } catch {
      await keycloak.login();
    }
  }

  const headers = new Headers(init.headers || {});
  if (keycloak.token) {
    headers.set('Authorization', `Bearer ${keycloak.token}`);
  }

  return fetch(input, {
    ...init,
    headers,
  });
}
