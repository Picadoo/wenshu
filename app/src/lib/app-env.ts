/** Static previews use hash routes so a copied reader URL also works on GitHub Pages. */
export const IS_PAGES_PREVIEW = import.meta.env.MODE === 'pages';
export const APP_BASE = import.meta.env.BASE_URL || '/';

export function appAssetUrl(path: string) {
  return `${APP_BASE}${path.replace(/^\/+/, '')}`;
}

export function appRouteUrl(path: string) {
  return IS_PAGES_PREVIEW ? `${APP_BASE}#${path}` : `${APP_BASE.replace(/\/$/, '')}${path}`;
}
