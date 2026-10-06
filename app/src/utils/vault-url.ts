export function encodeAssetUrl(url: string) {
  const origin = url.match(/^[a-z][a-z\d+.-]*:\/\/[^/]+/i)?.[0] ?? '';
  const path = url.slice(origin.length);
  const encodedPath = path
    .split('/')
    .map((part) => {
      try {
        return encodeURIComponent(decodeURIComponent(part));
      } catch {
        return encodeURIComponent(part);
      }
    })
    .join('/');
  return `${origin}${encodedPath}`;
}

export function joinAssetUrl(base: string, name: string) {
  const prefix = base.replace(/\/$/, '');
  return encodeAssetUrl(`${prefix}/${name}`);
}
