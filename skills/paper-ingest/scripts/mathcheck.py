"""Check LaTeX with the reader's bundled KaTeX before source review is sealed.

Rendering success proves syntax support, not equivalence to the PDF equation.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.config import load_config as load_skill_config  # noqa: E402


def check_renderable(md: str, wenshu: Path | None = None) -> list[str]:
    from translation import protected_spans

    spans = protected_spans(md)
    equations = [s for s in spans if s["kind"] in ("math_block", "math_inline")]
    pieces, cursor = [], 0
    for span in spans:
        pieces.append(md[cursor:span["start"]])
        cursor = span["end"]
    pieces.append(md[cursor:])
    if re.search(r"(?<!\\)\$", "".join(pieces)):
        return ["正文有未配对的数学 $ 分隔符；公式需闭合，普通美元符号须转义"]
    if not equations:
        return []
    if wenshu is None:
        config = Path(__file__).resolve().parents[1] / "config.json"
        wenshu = Path(load_skill_config(config)["wenshu"])
    katex = wenshu / "public/vendor/katex/katex.min.js"
    node = shutil.which("node")
    if not node or not katex.is_file():
        return ["公式渲染检查缺少现有 Node 或文枢 bundled KaTeX；不能记录源稿审核通过"]
    items = []
    for s in equations:
        block = s["kind"] == "math_block"
        width = 2 if block else 1
        items.append({"tex": s["text"][width:-width], "displayMode": block,
                      "line": md.count("\n", 0, s["start"]) + 1})
    script = """
const fs = require('node:fs');
const vm = require('node:vm');
const sandbox = {module: {exports: {}}};
sandbox.exports = sandbox.module.exports;
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), sandbox);
const katex = sandbox.module.exports;
const items = JSON.parse(fs.readFileSync(0, 'utf8'));
const errors = [];
for (const item of items) {
  try {
    katex.renderToString(item.tex, {displayMode: item.displayMode,
      throwOnError: true, strict: 'ignore', trust: false, maxExpand: 1000});
  } catch (e) { errors.push({line: item.line, message: e.message}); }
}
process.stdout.write(JSON.stringify(errors));
"""
    try:
        result = subprocess.run([node, "-e", script, str(katex.resolve())],
                                input=json.dumps(items), text=True, encoding="utf-8",
                                capture_output=True, timeout=30,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            return [f"公式渲染检查失败：{result.stderr.strip()[:300]}"]
        return [f"正文行 {e['line']} LaTeX 不能渲染：{e['message']}"
                for e in json.loads(result.stdout)]
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return [f"公式渲染检查未完成：{exc}"]
