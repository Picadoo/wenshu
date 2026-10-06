// 桌面构建收尾：把 dist/vault 从嵌入产物里剥掉。
// vault（1GB+）嵌进二进制会把 rlib 撑爆（E0786 corrupt metadata）；
// 桌面版运行时经 Rust 侧 vault:// 协议直接从磁盘读（见 src-tauri/src/lib.rs）。
import { rmSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const dist = fileURLToPath(new URL('../dist/vault', import.meta.url));
if (existsSync(dist)) {
  rmSync(dist, { recursive: true, force: true });
  console.log('已剥离 dist/vault（桌面版 vault 走磁盘协议，不嵌入二进制）');
} else {
  console.log('dist/vault 不存在，跳过');
}
