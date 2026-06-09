#!/usr/bin/env python3
"""把 经典版(index.html + aha.css + main.js + 数据)打包成一个
双击即可打开、无需服务器的单文件 aha-standalone.html。"""
import json, re, pathlib
ROOT = pathlib.Path("/home/ubuntu/users/qiuyiwu/aha-art-demo")

css  = (ROOT/"css/aha.css").read_text(encoding="utf-8")
js   = (ROOT/"js/main.js").read_text(encoding="utf-8")
works= json.load(open(ROOT/"data/artworks.json", encoding="utf-8"))
graph= json.load(open(ROOT/"data/graph.json", encoding="utf-8"))
html = (ROOT/"index.html").read_text(encoding="utf-8")

# 1) 把 fetch 加载替换成读取内联数据
js = re.sub(
    r"\[WORKS, GRAPH\] = await Promise\.all\(\[.*?\]\);",
    "WORKS = window.__AHA.works; GRAPH = window.__AHA.graph;",
    js, flags=re.S)
assert "window.__AHA.works" in js and "fetch('data" not in js, "fetch 替换失败"

data_js = "window.__AHA=" + json.dumps({"works": works, "graph": graph}, ensure_ascii=False) + ";"
assert "</script" not in (data_js + js).lower(), "内容里出现了 </script>,需转义"

# 2) 内联 CSS
html = html.replace('<link rel="stylesheet" href="css/aha.css" />',
                    "<style>\n" + css + "\n</style>")
# 3) 内联脚本(去掉 module,先注入数据)
html = html.replace('<script type="module" src="js/main.js"></script>',
                    "<script>\n" + data_js + "\n" + js + "\n</script>")

out = ROOT/"aha-standalone.html"
out.write_text(html, encoding="utf-8")
print(f"✓ 生成 {out.name}  ({out.stat().st_size//1024} KB) · {len(works)} 件作品 · {len(graph['edges'])} 条边")
print("  双击即可打开(file://),无需服务器。图片走 AIC CDN,联网时加载;离线则显示文字卡。")
