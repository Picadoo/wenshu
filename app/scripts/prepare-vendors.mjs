import { copyFileSync, cpSync, mkdirSync } from 'node:fs';

// Generated from the locked npm packages, so the renderer and mathcheck use one version.
mkdirSync('public/vendor/katex', { recursive: true });
copyFileSync('node_modules/marked/lib/marked.umd.js', 'public/vendor/marked.min.js');
copyFileSync('node_modules/marked/LICENSE.md', 'public/vendor/marked-LICENSE.md');
for (const file of ['katex.min.js', 'katex.min.css']) copyFileSync('node_modules/katex/dist/' + file, 'public/vendor/katex/' + file);
copyFileSync('node_modules/katex/dist/contrib/auto-render.min.js', 'public/vendor/katex/auto-render.min.js');
copyFileSync('node_modules/katex/LICENSE', 'public/vendor/katex/LICENSE');
cpSync('node_modules/katex/dist/fonts', 'public/vendor/katex/fonts', { recursive: true });
