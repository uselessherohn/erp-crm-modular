/**
 * Tokens SOLO en memoria de módulo — nunca localStorage/sessionStorage
 * (XSS robaría el token directamente). Se pierde la sesión al refrescar la
 * pestaña, trade-off deliberado de seguridad para v1 de core; un refresh
 * token de vida más larga vía httpOnly cookie es la mejora natural para
 * cuando exista el módulo de infraestructura/despliegue — TODO explícito,
 * fuera de alcance de core v1 (regla 1, no adelantar).
 */
let accessToken: string | null = null;
let refreshToken: string | null = null;

const listeners = new Set<() => void>();

export function getAccessToken() {
  return accessToken;
}

export function getRefreshToken() {
  return refreshToken;
}

export function setTokens(access: string, refresh: string) {
  accessToken = access;
  refreshToken = refresh;
  listeners.forEach((l) => l());
}

export function clearTokens() {
  accessToken = null;
  refreshToken = null;
  listeners.forEach((l) => l());
}

export function isAuthenticated() {
  return accessToken !== null;
}

export function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
