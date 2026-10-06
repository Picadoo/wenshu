export const USE_WEB_IMAGES = false;
export function hasWebVariant(url: string) { return /\.(png|jpe?g)$/i.test(url); }
export function webImageUrl(url: string) { return url; }
