#!/usr/bin/env python3
# 策展候选名单:非 canon 艺术家按馆藏量 Top-N,预填可自动算的(身份/实测情绪·世界观/风格),
# 列出待人工补的缺口。输出 data/canon_candidates.json,供 kg-artist-candidates.html 评审。
# 用法:python3 build_canon_candidates.py [N]   (默认 120)
import json,os,sys,urllib.request,urllib.parse,psycopg2
from psycopg2.extras import RealDictCursor

N=int(sys.argv[1]) if len(sys.argv)>1 else 120
d=json.load(open(os.path.expanduser("~/.aha_pg.json")))
cn=psycopg2.connect(host=d.get('host','127.0.0.1'),port=d.get('port',5432),dbname=d['dbname'],user=d['user'],password=d['password'])
cur=cn.cursor(cursor_factory=RealDictCursor)
cur.execute("""WITH g AS (
  SELECT canonical_artist_id aid, max(name_cn) cn, max(name_en) en, max(east_west) ew,
         max(aha_kg_id) kg, count(*) FILTER (WHERE status<>'dup') n, count(*) FILTER (WHERE has_vlm) nvlm
  FROM v_ledger WHERE canonical_artist_id IS NOT NULL AND canonical_artist_id NOT LIKE '%%unknown%%'
       AND COALESCE(name_cn,name_en) IS NOT NULL GROUP BY canonical_artist_id)
  SELECT * FROM g WHERE kg IS NULL ORDER BY n DESC LIMIT %s""",(N,))
cands=cur.fetchall(); cn.close()

def api(aid):
    u="http://127.0.0.1:8094/artist?id="+urllib.parse.quote(aid)
    return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={'Host':'aha.yishujia.art'})))

out=[]
for i,c in enumerate(cands):
    try: dd=api(c['aid'])
    except Exception: dd={}
    m=dd.get('measured') or {}; vad=m.get('vad'); wv=m.get('wv') or {}
    vseed=({'v':vad['v']['mean'],'a':vad['a']['mean'],'d':(vad['d']['mean'] if vad.get('d') else None)} if vad and vad.get('v') else None)
    wseed=({'x':wv['x']['mean'],'y':wv['y']['mean']} if wv.get('x') else None)
    styles=[s['k'] for s in (dd.get('styles') or [])][:6]
    born=dd.get('born'); death=dd.get('death'); ew=c['ew']; birth=dd.get('region'); nat=dd.get('nationality')
    gaps=[]
    if not(born or death): gaps.append('生卒年')
    if not nat: gaps.append('国籍')
    if not vseed: gaps.append('情绪VAD(需kept+VLM)')
    if not wseed: gaps.append('世界观坐标(需kept+VLM)')
    if not styles: gaps.append('风格标注')
    gaps+=['生平 bio','世界观读法','师承谱系','画外音/创作观','一生轨迹']
    seed={'cn':c['cn'],'en':c['en'],'born':born,'death':death,'region':ew,'nationality':nat,'birthplace':birth,
          'styles':styles,'affect':vseed,'wv':wseed,
          'bio':None,'headline':None,'titles':[],'teachers':[],'peers':[],'students':[],
          'quote':None,'meaning':None,'voice_echo':None,'trajectory':[],'subjects':[],'style_relation':None,
          '_auto':'affect/wv/styles 取自 kept+VLM 真迹;其余待人工策展'}
    out.append({'rank':i+1,'aid':c['aid'],'cn':c['cn'],'en':c['en'],'region':ew,'birthplace':birth,
                'nationality':nat,'born':born,'death':death,'n_holdings':dd.get('n_holdings') or c['n'],
                'n_vlm':c['nvlm'],'n_kept_vlm':m.get('n_vad') or 0,'thumb':(dd.get('holdings') or [{}])[0].get('thumb'),
                'styles':styles,'measured':{'vad':vseed,'wv':wseed},
                'coverage':{'identity':bool(born or death),'measured_vad':bool(vseed),'measured_wv':bool(wseed),'styles':bool(styles)},
                'gaps':gaps,'seed':seed})
meta={'generated_note':'非 canon 艺术家按馆藏量 Top%d;auto 预填取自 kept+VLM 真迹(多数稀疏);人文字段待策展'%N,'total_noncanon':6472,'n':len(out)}
p='/data/pub/p/aha/data/canon_candidates.json'
json.dump({'meta':meta,'items':out},open(p,'w'),ensure_ascii=False,indent=1)
print("写出",len(out),"→",p,os.path.getsize(p),"bytes")
print("有实测VAD:",sum(1 for x in out if x['coverage']['measured_vad']),"| 有生卒:",sum(1 for x in out if x['coverage']['identity']),"| 有风格:",sum(1 for x in out if x['coverage']['styles']))
