"""把 data.json 内联进 index.html，生成单文件 share.html。
双击打开，无需任何网络/服务器。"""
import json
from pathlib import Path

ROOT = Path(__file__).parent
html = (ROOT / "index.html").read_text(encoding="utf-8")
data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))

inject = (
    "<script>window.__EMBEDDED_DATA__ = "
    + json.dumps(data, ensure_ascii=False)
    + ";</script>\n</head>"
)
out = html.replace("</head>", inject, 1)

(ROOT / "share.html").write_text(out, encoding="utf-8")
print(f"已生成 share.html ({len(out)//1024} KB)，可直接发送")
