import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
import { MessageChannel } from 'node:worker_threads';

const channels = [];
globalThis.MessageChannel = class extends MessageChannel {
  constructor() { super(); channels.push(this); }
};

const catalog = JSON.parse(readFileSync('public/vault/catalog.json', 'utf8'));
const terms = JSON.parse(readFileSync('public/vault/terms.json', 'utf8'));

// Render the actual product without a browser, server, credentials or external requests.
try {
for (const scenario of [
  { mode: 'production', route: '/dashboard', empty: false },
  { mode: 'pages', route: '/dashboard', empty: false },
  { mode: 'pages', route: '/dashboard', empty: true },
  { mode: 'pages', route: '/settings', empty: false },
  { mode: 'pages', route: '/dashboard/import', empty: false },
]) {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', { url: 'https://example.org/', pretendToBeVisual: true });
  for (const key of ['window', 'document', 'Node', 'Element', 'HTMLElement', 'DOMParser', 'NodeFilter', 'localStorage']) globalThis[key] = dom.window[key];
  Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true });
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const data = scenario.empty ? { ...catalog, count: 0, papers: [], topicDocs: [] } : catalog;
  globalThis.fetch = async (url) => {
    if (String(url).endsWith('/catalog.json')) return new Response(JSON.stringify(data));
    if (String(url).endsWith('/terms.json')) return new Response(JSON.stringify(scenario.empty ? { terms: [] } : terms));
    if (String(url).endsWith('/activity.json')) return new Response(JSON.stringify({ days: {}, papersByDay: {} }));
    throw new Error(`Unexpected request: ${url}`);
  };
  const compiled = await build({
    stdin: {
      contents: "import React from 'react'; import {createRoot} from 'react-dom/client'; import {MemoryRouter} from 'react-router'; import {App} from './src/app'; export {React,createRoot,MemoryRouter,App};",
      resolveDir: process.cwd(), loader: 'tsx',
    },
    bundle: true, write: false, format: 'esm', platform: 'browser', target: 'es2022', outfile: 'workspace-check.mjs',
    banner: { js: `/* ${JSON.stringify(scenario)} */` },
    define: {
      'process.env.NODE_ENV': '"development"', 'import.meta.env.PROD': 'false',
      'import.meta.env.BASE_URL': JSON.stringify(scenario.mode === 'pages' ? '/wenshu/' : '/'),
      'import.meta.env.MODE': JSON.stringify(scenario.mode),
    },
  });
  const source = compiled.outputFiles.find((file) => file.path.endsWith('.mjs'));
  const module = await import(`data:text/javascript;base64,${Buffer.from(source.text).toString('base64')}`);
  const root = module.createRoot(document.getElementById('root'));
  try {
    await module.React.act(async () => root.render(module.React.createElement(module.MemoryRouter, { initialEntries: [scenario.route] }, module.React.createElement(module.App))));
    await module.React.act(async () => { await new Promise((done) => setTimeout(done, 10)); });
    const text = document.body.textContent;
    assert.ok(!text.includes('开始读示例') && !text.includes('示例预览') && !text.includes('公开示例 · 阅读体验'));
    assert.equal(document.querySelector('.preview-banner'), null);
    if (scenario.route === '/dashboard') {
      assert.ok(text.includes('我的文库') && text.includes('添加论文'));
      assert.ok(scenario.empty ? text.includes('还没有论文') : text.includes(catalog.papers[0].title));
      if (!scenario.empty) assert.ok(text.includes('最近阅读'));
    }
    if (scenario.route === '/settings') assert.ok(text.includes('保存 AI 配置') && text.includes('服务器地址'));
    if (scenario.route === '/dashboard/import') assert.ok(text.includes('复制入库指令') && text.includes('本机 PDF 路径'));
    process.stdout.write(`PASS: ${scenario.mode} ${scenario.route} (${scenario.empty ? 'empty' : 'existing'} library)\n`);
  } finally {
    await module.React.act(async () => root.unmount());
    dom.window.close();
  }
}
} finally {
  for (const channel of channels) {
    channel.port1.close();
    channel.port2.close();
  }
}
