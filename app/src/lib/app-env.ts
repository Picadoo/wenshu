/** GitHub Pages needs hash routes; hosting does not change product features. */
export const USES_HASH_ROUTING = import.meta.env.MODE === 'pages';
export const APP_BASE = import.meta.env.BASE_URL || '/';

export function appAssetUrl(path: string) {
  return `${APP_BASE}${path.replace(/^\/+/, '')}`;
}

export function appRouteUrl(path: string) {
  return USES_HASH_ROUTING ? `${APP_BASE}#${path}` : `${APP_BASE.replace(/\/$/, '')}${path}`;
}
