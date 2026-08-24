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

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'ApiError';
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }
}

/** Fetch JSON, turning non-2xx responses into a typed ApiError. */
export async function apiFetchJson<T>(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<T> {
  const res = await apiFetch(input, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(body?.detail || `Request failed (${res.status})`, res.status);
  }
  return res.json() as Promise<T>;
}
