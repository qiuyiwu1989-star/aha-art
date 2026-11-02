from pathlib import Path
import json,html
rows=[
 ('首页连续浏览','已实现，部分验收','24件追加；远处图片与画框回收；72件浏览后详情返回锚点约15px偏差。','100页真机、堆平台期与轻量占位上限仍待验收。'),
 ('作品引用与页面迁移','已实现，部分验收','历史/收藏/草稿/旧链接按引用解析；选画服务端搜索及游标分页。','登录与保存需隔离写入环境。'),
 ('策展与展览','已实现，部分验收','规则聚合、意图全域评分、12轴相似度；新接口串行HTTP断言通过。','冷查询仍约2–5秒；正式服务索引与缓存继续优化。'),
 ('图谱详情','已实现，测试通过','4000条完整数据64分片，8片缓存；逐条一致性校验。','发布须页面与分片原子更新，缺片可重试。'),
 ('点云传输','已实现，测试通过','各20000点无损编码；gzip实测约776KB/759KB。','仍全点解码；视口加载与GPU预算未完成。'),
 ('图片健康','抽样完成，资产待修','16张抽样均有效；另发现34754云端ImageTooLarge。','本地派生脚本与回填清单已备，真实资产未修复。'),
 ('3D与字体','已实现，部分验收','隐藏停止、拾取按变化/33ms节流；主要页字体非阻塞。','保留DPR和导出；真实GPU帧时与真机导出待测。'),
 ('后台','部分完成','特展与档案不再取8000；轮询与筛选竞态治理。','画框全库统计仍1处例外，需等价后端规则聚合。'),
 ('本地服务基础','已实现，测试通过','图片/API隔离槽；资源锁释放；512MiB磁盘缓存预算；静态压缩/ETag。','本地SSH适配器不可部署为生产API。'),
 ('正式服务与数据库','待运行端确认','已确认122入口经18772反向隧道，来源与wg-ai节点同公网地址；线上首页与122发布目录一致。','AI侧10.255.122.2可达但现有身份登录被拒；需核实实际进程、版本，再准备正式接入。'),
 ('发布验收','待条件齐备','回归脚本、静态资源门禁、回滚边界已整理。','真实账号写入、SW升级、弱网手机、容量测试、回滚演练。')]
cards=''.join('<article data-state="'+('pending' if '待' in status or '部分' in status else 'done')+'"><header><h2>'+name+'</h2><span>'+status+'</span></header><p>'+done+'</p><p class="muted">接续：'+todo+'</p></article>' for name,status,done,todo in rows)
page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AHA 性能优化进度</title><style>
:root{--ground:#f2eee5;--surface:#fffdf8;--ink:#292820;--muted:#726c61;--line:#d6cdbc;--accent:#a9552e}*{box-sizing:border-box}:root[data-theme=dark]{--ground:#1b1d1c;--surface:#252927;--ink:#efe9dd;--muted:#b9b2a5;--line:#45483f;--accent:#e9a578}@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--ground:#1b1d1c;--surface:#252927;--ink:#efe9dd;--muted:#b9b2a5;--line:#45483f;--accent:#e9a578}}body{margin:0;background:var(--ground);color:var(--ink);font:16px/1.8 -apple-system,"PingFang SC",sans-serif}main{max-width:1040px;margin:auto;padding:36px 22px}h1{font:36px/1.4 Georgia,"Songti SC",serif}h2{font-size:19px;margin:0}article{padding:22px;border:1px solid var(--line);background:var(--surface);margin:14px 0;border-radius:10px}header{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}span,a{color:var(--accent)}.muted{color:var(--muted)}button{border:1px solid var(--line);background:var(--surface);color:var(--ink);padding:8px 14px;border-radius:6px;cursor:pointer}nav{display:flex;gap:10px;flex-wrap:wrap}.note{border-left:3px solid var(--accent);padding:10px 18px}article[hidden]{display:none}</style><main><button id="theme">切换明暗</button><p class="muted">2026-10-26 · 本地隔离预览 8766</p><h1>AHA 性能优化进度</h1><p class="note">已经落地主要阅读链路和数据减负；不是整站验收完成，也尚未生产发布。全站继续沿用既有 AHA 样式。用户已确认继续执行，以下未完成项已纳入后续工作。</p><nav><button data-filter="all">全部任务</button><button data-filter="pending">仍需接续</button><button data-filter="done">测试通过项</button></nav>'''+cards+'''<p class="muted">证据：docs/batch-2-verification.md、tests/catalog-http.json、tests/query-evidence.json、tests/image-health-sample.json。接口数字是本机串行采样，非公网SLA；16张图片样本不代表全库。</p><p>回滚：停止8766即可继续使用原8765；生产未变更。</p></main><script>document.getElementById('theme').onclick=()=>document.documentElement.dataset.theme=document.documentElement.dataset.theme==='dark'?'light':'dark';document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>document.querySelectorAll('article').forEach(a=>a.hidden=b.dataset.filter!=='all'&&a.dataset.state!==b.dataset.filter));</script></html>'''
Path('docs/diagrams/2026-10-26-aha-performance-progress.html').write_text(page)
Path('docs/diagrams/README.md').write_text('- [2026-10-26 AHA 性能优化进度](2026-10-26-aha-performance-progress.html) — 已实现、验证证据与仍需接续任务。\n')
