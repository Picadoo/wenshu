import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
import { marked } from 'marked';

const catalog = JSON.parse(readFileSync('public/vault/catalog.json', 'utf8'));
const terms = JSON.parse(readFileSync('public/vault/terms.json', 'utf8'));
assert.equal(catalog.papers.length, 1, 'the preview must contain exactly one example paper');

// Exercise actual hydration, renderer and vendor loading without launching a browser/server.
for (const scenario of [
  { mode: 'production', base: '/', origin: 'http://localhost:8080', vault: '/vault' },
  { mode: 'pages', base: '/wenshu/', origin: 'https://picadoo.github.io', vault: '/wenshu/vault' },
  { mode: 'production', base: '/', origin: 'http://tauri.localhost', vault: 'http://vault.localhost/vault', desktop: true },
]) {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: scenario.origin + scenario.base, runScripts: 'outside-only' });
  for (const key of ['window', 'document', 'Node', 'Element', 'HTMLElement', 'DOMParser', 'NodeFilter']) globalThis[key] = dom.window[key];
  if (scenario.desktop) dom.window.__TAURI_INTERNALS__ = {};
  dom.window.marked = marked;
  dom.window.eval(readFileSync('public/vendor/katex/katex.min.js', 'utf8'));
  dom.window.eval(readFileSync('public/vendor/katex/auto-render.min.js', 'utf8'));
  const compiled = await build({
    stdin: { contents: "export * from './src/lib/app-env'; export * from './src/data/vault'; export * from './src/data/hydrate-vault'; export * from './src/data/papers'; export * from './src/lib/markdown';", resolveDir: resolve('.'), loader: 'ts' },
    bundle: true, write: false, format: 'esm', platform: 'browser', target: 'es2022',
    banner: { js: `/* Asset scenario: ${scenario.origin} */` },
    define: { 'import.meta.env.PROD': 'true', 'import.meta.env.BASE_URL': JSON.stringify(scenario.base), 'import.meta.env.MODE': JSON.stringify(scenario.mode) },
  });
  const module = await import('data:text/javascript;base64,' + Buffer.from(compiled.outputFiles[0].text).toString('base64'));
  assert.equal(module.USES_HASH_ROUTING, scenario.mode === 'pages');
  assert.equal(module.VAULT_CONTRACT.catalog, scenario.vault + '/catalog.json');
  const originalFetch = globalThis.fetch;
  const requested = [];
  globalThis.fetch = async (url) => {
    requested.push(url);
    assert.ok(String(url).startsWith(scenario.vault + '/'), 'hydration must respect the deployment root');
    if (String(url).endsWith('/catalog.json')) return new Response(JSON.stringify(catalog));
    if (String(url).endsWith('/terms.json')) return new Response(JSON.stringify(terms));
    return new Response('{}');
  };
  try { await module.hydrateVaultData(); } finally { globalThis.fetch = originalFetch; }
  assert.equal(requested.length, 3);
  assert.equal(module.papers.length, 1);
  const paper = module.papers[0];
  assert.ok(paper.files.article.startsWith(scenario.vault + '/'));
  assert.ok(paper.files.pdf.startsWith(scenario.vault + '/'));
  assert.ok(paper.coverUrl.startsWith(scenario.vault + '/'));
  assert.ok(paper.images.every((image) => image.url.startsWith(scenario.vault + '/')));
  assert.equal(module.withVaultOrigin(paper).files.article, paper.files.article, 'mapping must be idempotent');
  const source = '# Test\n\n## Section\n\n![Figure](/vault/papers/example/images/图1.png)\n\n[PDF](/vault/papers/example/content/paper.pdf)\n\nInline $x^2$ and display $$\\frac{a}{b}$$.';
  const rendered = module.renderMarkdown(source);
  const root = document.createElement('div'); root.innerHTML = rendered.html;
  assert.equal(decodeURIComponent(root.querySelector('img').getAttribute('src')), scenario.vault + '/papers/example/images/图1.png');
  assert.equal(root.querySelector('a').getAttribute('href'), scenario.vault + '/papers/example/content/paper.pdf');
  module.typesetMath(root);
  assert.equal(root.querySelectorAll('.katex').length, 2);
  const readerRoute = '/dashboard/papers/' + paper.slug;
  assert.equal(module.appRouteUrl(readerRoute), scenario.mode === 'pages' ? '/wenshu/#' + readerRoute : readerRoute);
  assert.equal(module.appRouteUrl('/share/test-token'), scenario.mode === 'pages' ? '/wenshu/#/share/test-token' : '/share/test-token');
  const vendorReady = module.ensureMarkdownVendors();
  assert.equal(document.querySelector('link[data-vendor]').getAttribute('href'), scenario.base + 'vendor/katex/katex.min.css');
  for (const file of ['marked.min.js', 'katex/katex.min.js', 'katex/auto-render.min.js']) {
    const script = document.querySelector(`script[data-vendor="${scenario.base}vendor/${file}"]`);
    assert.ok(script, 'vendor must be requested beneath Vite base');
    script.dispatchEvent(new dom.window.Event('load'));
    await new Promise((done) => setImmediate(done));
  }
  await vendorReady;
  globalThis.fetch = async (url) => {
    if (String(url).endsWith('/catalog.json')) return new Response(JSON.stringify({ papers: [], topicDocs: [] }));
    if (String(url).endsWith('/terms.json')) return new Response(JSON.stringify({ terms: [] }));
    return new Response(JSON.stringify({ days: {}, papersByDay: {} }));
  };
  try {
    await module.hydrateVaultData();
    assert.equal(module.papers.length, 0, 'an empty library must not be replaced with the example');
    globalThis.fetch = async () => new Response(null, { status: 503 });
    await module.hydrateVaultData();
    assert.equal(module.papers.length, 0, 'failed refresh must preserve a deliberately empty library');
  } finally {
    globalThis.fetch = originalFetch;
  }
  dom.window.close();
}
process.stdout.write('Pages, local Web and desktop asset/hydration/Markdown checks passed.\n');
