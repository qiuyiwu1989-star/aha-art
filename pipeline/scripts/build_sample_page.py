#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成数据样本可视化页:各源真图缩略 + 三表标签结构 + 跨源匹配对照。
输出 /data/pub/p/aha/data-sample.html (线上 aha.yishujia.art/data-sample.html)。"""
import json, html, psycopg2
from qcloud_cos import CosConfig, CosS3Client

d=json.load(open('/home/ubuntu/.aha_pg.json'))
con=psycopg2.connect(host=d['host'],port=d['port'],dbname=d['dbname'],user=d['user'],password=d['password']);cur=con.cursor()
cd=json.load(open('/home/ubuntu/.aha_cos.json'))
COS=CosS3Client(CosConfig(Region=cd['region'],SecretId=cd['secret_id'],SecretKey=cd['secret_key']))
def url(key): return COS.get_presigned_url(Method='GET',Bucket='aha-1254041526',Key=key,Expired=7*86400)

def samples(like,n=4,need_subj=False):
    cond = "and exists(select 1 from work_subjects ss where ss.work_id=w.work_id)" if need_subj else ""
    cur.execute(f"""select w.work_id,w.title,w.year,w.school,w.medium,w.w_cm,w.h_cm,w.source_batch,w.src_work_id,w.status,
      f.cos_key,f.width,f.height,f.bytes,f.phash, a.name_cn,a.name_en,a.born,a.death,a.region,
      (select array_agg(subject) from work_subjects s where s.work_id=w.work_id),
      (w.vlm->>'fused')
      from works w join files f on f.file_id=w.primary_file_id left join artists a on a.artist_id=w.artist_id
      where w.source_batch like %s and f.cos_key is not null {cond} order by random() limit %s""",(like,n*3))
    out=[]
    for r in cur.fetchall():
        if not r[1] and like!='yishujia%' : continue   # 非yishujia挑有标题的
        out.append(r)
        if len(out)>=n: break
    return out

def card(r):
    (wid,title,year,school,medium,wcm,hcm,sb,swid,status,key,w,h,by,ph,acn,aen,born,death,region,subs,vlm)=r
    art=acn or aen or '—'
    if born: art+=f" ({born}–{death or ''})"
    rows=[]
    if title: rows.append(("标题",title))
    rows.append(("艺术家",art))
    meta=" · ".join(x for x in [str(year) if year else "",school or "",medium or "",
          (f"{wcm:.0f}×{hcm:.0f}cm" if wcm and hcm else "")] if x)
    if meta: rows.append(("元数据",meta))
    if subs: rows.append(("题材标签"," · ".join(subs)))
    fused=""
    if vlm:
        try: vj=json.loads(vlm); fused="；".join(f"{k}:{v}" for k,v in list(vj.items())[:4] if isinstance(v,str))[:160]
        except: fused=str(vlm)[:160]
    if fused: rows.append(("VLM标注",fused))
    meta_rows="".join(f'<tr><td>{html.escape(k)}</td><td>{html.escape(str(v))}</td></tr>' for k,v in rows)
    return f'''<div class="card">
      <img loading="lazy" src="{html.escape(url(key))}">
      <div class="meta"><table>{meta_rows}</table>
        <div class="tech">{w}×{h} · {by//1024}KB · phash <code>{ph}</code><br>
        <span class="st {status}">{status}</span> <code class="k">{html.escape(key)}</code></div>
      </div></div>'''

SECTIONS=[("YH 油画","yh%","文件名 JOIN 四张 MySQL 表 → 标题/作者/年代/材质齐全；高清"),
          ("WikiArt","wikiart%","文件夹路径即标签（流派/艺术家/标题）；缩略图级"),
          ("nbfox 麦田","nbfox%","jsonl 元数据按文件名 slug 配图；含浮世绘等"),
          ("yishujia","yishujia%","ULID 裸图零元数据 → 标签全靠下游 VLM 看图生成；高清")]
secs=[]
for name,like,desc in SECTIONS:
    cards="".join(card(r) for r in samples(like,4,need_subj=(like=='yh%')))
    secs.append(f'<h2>{name} <span class="d">{desc}</span></h2><div class="grid">{cards}</div>')

# 跨源匹配对照
cur.execute("""select dc.member_file_ids from dup_clusters dc where dc.reason like 'xsrc%' and array_length(dc.member_file_ids,1)=2 limit 60""")
pair_html=""
for (fids,) in cur.fetchall():
    cur.execute("""select split_part(w.source_batch,':',1),w.title,f.cos_key,f.width,f.height,f.phash
       from files f join works w on w.work_id=f.work_id where f.file_id=any(%s)""",(fids,))
    m=cur.fetchall()
    if len({x[0] for x in m})>=2 and all(x[2] for x in m):
        cells="".join(f'''<div class="card"><img loading="lazy" src="{html.escape(url(x[2]))}">
          <div class="meta"><table><tr><td>来源</td><td><b>{x[0]}</b></td></tr>
          <tr><td>标题</td><td>{html.escape((x[1] or '无题')[:30])}</td></tr>
          <tr><td>尺寸</td><td>{x[3]}×{x[4]}</td></tr></table>
          <div class="tech">phash <code>{x[5]}</code></div></div></div>''' for x in m)
        pair_html=f'<div class="grid match">{cells}</div><p class="mn">↑ 同一幅画，phash 相同 → 判为同画，择优留高清</p>'
        break

doc=f'''<!doctype html><html lang=zh><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>aha 数据样本</title>
<style>
body{{margin:0;font:14px/1.6 -apple-system,"PingFang SC",sans-serif;background:#f5f3ee;color:#1a1a1a}}
header{{padding:16px 22px;background:#fff;border-bottom:1px solid #e6e3dd}}
h1{{font-size:18px;margin:0}} .wrap{{max-width:1180px;margin:0 auto;padding:18px 22px}}
h2{{font-size:15px;margin:26px 0 10px}} h2 .d{{font-weight:400;color:#9a6a3a;font-size:12px;margin-left:8px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}}
.card{{background:#fff;border:1px solid #e6e3dd;border-radius:10px;overflow:hidden}}
.card img{{width:100%;height:200px;object-fit:cover;display:block;background:#eee}}
.meta{{padding:10px 12px}} .meta table{{width:100%;border-collapse:collapse;font-size:12.5px}}
.meta td{{vertical-align:top;padding:2px 0}} .meta td:first-child{{color:#9a6a3a;width:62px;white-space:nowrap}}
.tech{{margin-top:7px;font-size:10.5px;color:#9a9a9a}} .tech code{{font-size:10px}} .tech .k{{word-break:break-all;color:#b08}}
.st{{display:inline-block;padding:0 6px;border-radius:8px;font-size:10px;color:#fff;margin-right:4px}}
.st.kept{{background:#3a8a5a}}.st.pending{{background:#c2792e}}.st.dup{{background:#9a9a9a}}.st.archived{{background:#888}}.st.rejected{{background:#b5483a}}
.match .card{{border:2px solid #9a6a3a}} .mn{{color:#9a6a3a;font-size:12.5px}}
</style></head><body>
<header><h1>aha 数据样本 · 各源标注方式 & 跨源匹配</h1></header>
<div class="wrap">{''.join(secs)}
<h2>跨源匹配机制 <span class="d">phash 把同一幅画在不同库里认出来（"逛数据"的底层）</span></h2>
{pair_html}</div></body></html>'''
open("/data/pub/p/aha/data-sample.html","w").write(doc)
print("写 /data/pub/p/aha/data-sample.html  (", len(doc), "字节 )")
