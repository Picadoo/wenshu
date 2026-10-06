import { existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';

// Only seed an empty checkout; never overwrite a user's synchronized library.
if (!existsSync('public/vault/catalog.json')) {
  const result = spawnSync('python', ['scripts/sync-vault.py', '--vault', '../examples/vault', '--no-activity'], { stdio: 'inherit' });
  if (result.error) { process.stderr.write(result.error.message + '\n'); process.exit(1); }
  process.exit(result.status ?? 1);
}
