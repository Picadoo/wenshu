import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

export default defineConfig(({ mode }) => ({
  base: mode === 'pages' ? '/wenshu/' : '/',
  plugins: [react()],
  resolve: { alias: { src: fileURLToPath(new URL('./src', import.meta.url)) } },
  server: { port: 8080, strictPort: true, proxy: { '/api': 'http://127.0.0.1:8787' } },
  build: { target: 'es2022' },
}));
