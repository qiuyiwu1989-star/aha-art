# coding: utf-8
# Sent over SSH stdin; never persisted remotely. Every operation uses a read-only transaction.
import json,os,base64,re,hashlib,math
from urllib.parse import quote,unquote,urlsplit
import psycopg2
from psycopg2.extras import RealDictCursor
P=REQUEST
cfg=json.load(open(os.path.expanduser('~/.aha_pg.json')))
c=psycopg2.connect(**{k:cfg[k] for k in ('host','port','dbname','user','password')},connect_timeout=5)
c.set_session(readonly=True)
def q(sql,args=()):
 with c.cursor(cursor_factory=RealDictCursor) as cur:
  cur.execute(sql,args or None);return [dict(r) for r in cur.fetchall()] if cur.description else []
q("SET LOCAL statement_timeout='8000ms'")
BASE=" FROM works w JOIN artists a ON a.artist_id=w.artist_id JOIN files f ON f.file_id=w.primary_file_id LEFT JOIN artists_canon ac ON ac.canon_id=a.aha_kg_id LEFT JOIN styles s ON s.style_id=w.style_id "
WV="substring(w.vlm->'worldview'->>'wv' from 'WV[1-6]')"
def num(expr):return "CASE WHEN ("+expr+") ~ '^-?[0-9]+([.][0-9]+)?$' THEN ("+expr+")::double precision END"
X=num("w.vlm->'worldview'->>'x'");Y=num("w.vlm->'worldview'->>'y'")
where="w.exhibited AND "+WV+" IS NOT NULL AND "+X+" IS NOT NULL AND "+Y+" IS NOT NULL";args=[]
# Product scope remains on-wall, coordinate-bearing catalog; details may resolve any known work.
if P.get('collection'):where='w.work_id IN (SELECT work_id FROM collection_works WHERE collection_id=%s)';args=[int(P['collection'])]
for key,col in [('wv',WV),('emo',"w.vlm->'affect'->>'primary_anchor'"),('artist',"COALESCE(ac.cn,a.name_cn,a.name_en,'佚名')")]:
 if P.get(key):where+=' AND '+col+'=%s';args.append(P[key])
if P.get('q'):
 term='%'+P['q'].replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
 where+=' AND (w.title ILIKE %s OR a.name_cn ILIKE %s OR a.name_en ILIKE %s OR w.accession_code ILIKE %s)';args.extend([term]*4)
if P.get('region'):where+=' AND a.region=%s';args.append(P['region'])
if P.get('style'):where+=' AND w.style_id=%s';args.append(int(P['style']))
for key,col in [('subject',"w.vlm->>'subject'"),('style_name','s.name_zh')]:
 if P.get(key):where+=' AND '+col+'=%s';args.append(P[key])
if P.get('min_quality'):where+=' AND w.quality>=%s';args.append(float(P['min_quality']))
cap=None
if P.get('rule'):
 P['_special']={'rule':json.loads(P['rule'])}
if P.get('_special'):
 sp=P['_special'];rule=sp.get('rule') or {};files=sp.get('work_ids') or []
 if files:
  keys=[]
  for file in files:
   path=unquote(urlsplit(str(file)).path).lstrip('/');keys.extend([path,path.removeprefix('img/')])
  where+=' AND f.cos_key=ANY(%s)';args.append(keys)
 else:
  for key,col in [('wv',WV),('emo',"w.vlm->'affect'->>'primary_anchor'")]:
   if rule.get(key):where+=' AND '+col+'=ANY(%s)';args.append(rule[key] if isinstance(rule[key],list) else [rule[key]])
  if rule.get('region'):where+=' AND a.region=%s';args.append(rule['region'])
 if rule.get('limit'):cap=max(1,int(rule['limit']))
FIELDS=['构图与组织','透视与空间','形状与造型','光影与明暗','色彩系统','笔触与肌理','边缘与节奏'];SHORT=['构图','空间','造型','光影','色彩','笔触','边缘'];NAMES=['摹写之眼','礼制图式','写意寄情','经验之光','表现外化','形式建构']
def item(r):
 v=r['vlm'] or {};wv=v.get('worldview') or {};af=v.get('affect') or {};vd=af.get('vad') or {};l=v.get('language7') or {};fr=v.get('frame') or {};fr=fr if isinstance(fr,dict) else {};key=r['cos_key'];file=('/'+key) if key.startswith('img/') else '/img/'+quote(key,safe='/')
 m=re.search('WV[1-6]',str(wv.get('wv','')));wvk=m.group() if m else None
 lang={short:(l.get(full,{}).get('v') if isinstance(l.get(full),dict) else l.get(full)) for full,short in zip(FIELDS,SHORT)}
 width=r.get('width');height=r.get('height')
 return dict(work_id=r['work_id'],code=r['accession_code'],file=file,thumb=file if key.startswith('img/') else file+'?imageMogr2/thumbnail/600x600/format/webp/quality/82',title=r['title'] or '无题',artist=r['artist'],aid=r['aha_kg_id'] or r['artist_id'],canon_id=r['aha_kg_id'],year=r['year'],region=r['region'],wv=wvk,wvcn=NAMES[int(wvk[-1])-1] if wvk else None,x=wv.get('x'),y=wv.get('y'),emo=af.get('primary_anchor'),vad=dict(v=vd.get('valence'),a=vd.get('arousal'),d=vd.get('dominance')),lang=lang,color=v.get('color'),quality=float(r['quality']) if r['quality'] is not None else None,style=r['style_zh'],style_id=r['style_id'],medium=v.get('media'),subject=v.get('subject'),voiceover=v.get('voiceover'),frame_suggest=fr.get('key'),frame_why=fr.get('why'),frame_finish=fr.get('finish'),frame_conf=fr.get('conf'),width=width,height=height,ar=width/height if width and height else None)
SELECT="SELECT w.work_id,w.accession_code,w.title,w.artist_id,w.year,w.quality,w.vlm,w.style_id,a.region,a.aha_kg_id,COALESCE(ac.cn,a.name_cn,a.name_en,'佚名') artist,s.name_zh style_zh,f.cos_key,f.width,f.height"
def rows(cond,params,n):return [item(r) for r in q(SELECT+BASE+' WHERE '+cond+' ORDER BY w.quality DESC NULLS LAST,w.work_id ASC LIMIT %s',params+[n])]
def browse():
 n=max(1,min(60,int(P.get('limit',24))));cond=where;pa=args[:];pos=0
 signature=hashlib.sha256(json.dumps({k:P.get(k) for k in ['wv','emo','artist','collection','_special','q','region','style','min_quality','subject','style_name']},sort_keys=True).encode()).hexdigest()[:16]
 if P.get('cursor'):
  token=json.loads(base64.urlsafe_b64decode(P['cursor']))
  if token.get('filter')!=signature:raise ValueError('cursor filter mismatch')
  quality=token['q'];wid=int(token['id']);pos=int(token['pos'])
  if quality is None:cond+=' AND w.quality IS NULL AND w.work_id>%s';pa+=[wid]
  else:cond+=' AND (w.quality<%s OR w.quality IS NULL OR (w.quality=%s AND w.work_id>%s))';pa += [float(quality),float(quality),wid]
 if cap:n=min(n,max(0,cap-pos))
 if n==0:return dict(items=[],has_more=False,next_cursor=None)
 rr=rows(cond,pa,n+1);more=len(rr)>n and (cap is None or pos+n<cap);rr=rr[:n]
 cursor=base64.urlsafe_b64encode(json.dumps(dict(q=rr[-1]['quality'],id=rr[-1]['work_id'],pos=pos+len(rr),filter=signature)).encode()).decode() if more else None
 return dict(items=rr,has_more=more,next_cursor=cursor)
def regavg():
 extracts=[];avgs=[]
 for i,(full,short) in enumerate(zip(FIELDS,SHORT)):
  full=full.replace("'","''");val="CASE WHEN jsonb_typeof(w.vlm->'language7'->'"+full+"')='object' THEN w.vlm->'language7'->'"+full+"'->>'v' ELSE w.vlm->'language7'->>'"+full+"' END"
  extracts.append(val+' AS v'+str(i));avgs.append('avg('+num('v'+str(i))+') AS "'+short+'"')
 sql='WITH vals AS MATERIALIZED (SELECT '+WV+' key,'+','.join(extracts)+BASE+' WHERE '+where+') SELECT key,'+','.join(avgs)+' FROM vals GROUP BY key'
 return {r['key']:{k:r[k] for k in SHORT} for r in q(sql,args) if r['key']}
route=P['route']
if route in ('browse','home'):
 out=browse()
 if route=='home':out.update(cover=out['items'][0] if out['items'] else None,sections=[],total=None)
elif route=='catalog-facets':
 columns={'style':'s.name_zh','subject':"w.vlm->>'subject'",'emo':"w.vlm->'affect'->>'primary_anchor'",'wv':WV}
 sql='WITH scope AS MATERIALIZED (SELECT '+','.join(col+' AS '+key for key,col in columns.items())+BASE+' WHERE '+where+') '
 sql+=' UNION ALL '.join("(SELECT '"+key+"' kind,"+key+" value,count(*) n FROM scope WHERE "+key+" IS NOT NULL GROUP BY "+key+" ORDER BY count(*) DESC"+('' if key=='emo' else ' LIMIT 24')+')' for key in columns)
 facets={key:[] for key in columns}
 for r in q(sql,args):facets[r['kind']].append([r['value'],r['n']])
 out={'facets':facets}
elif route=='curate-match':
 match=json.loads(P['match']);score=[];pa=[]
 bag="concat_ws(' ',w.vlm->>'subject',w.vlm->'affect'->>'primary_anchor',s.name_zh,w.vlm->>'voiceover',w.title)"
 for theme in match.get('themes',[]):
  score.append('CASE WHEN strpos('+bag+',%s)>0 THEN 2 ELSE 0 END');pa.append(theme)
 for flag,region,weight in [('east','east',2),('west','west',1)]:
  if match.get(flag):score.append('CASE WHEN a.region=%s THEN '+str(weight)+' ELSE 0 END');pa.append(region)
 for constraint in match.get('constraints',[]):
  for key,axis,op in [('vlt','valence','<='),('vgt','valence','>='),('aLt','arousal','<='),('agt','arousal','>=')]:
   if constraint.get(key) is not None:
    score.append('CASE WHEN '+num("w.vlm->'affect'->'vad'->>'"+axis+"'")+op+'%s THEN 1 ELSE 0 END');pa.append(float(constraint[key]))
  if constraint.get('region'):score.append('CASE WHEN a.region=%s THEN 1 ELSE 0 END');pa.append(constraint['region'])
 pick=match.get('pick',{})
 for key,col in [('styles','s.name_zh'),('subjects',"w.vlm->>'subject"),('emotions',"w.vlm->'affect'->>'primary_anchor")]:
  if pick.get(key):score.append('CASE WHEN '+col+'=ANY(%s) THEN 2 ELSE 0 END');pa.append(pick[key])
 for keyword in pick.get('keywords',[]):
  if keyword:
   score.append("CASE WHEN strpos(lower(concat_ws(' ',w.title,COALESCE(ac.cn,a.name_cn,a.name_en),s.name_zh,w.vlm->>'subject')),%s)>0 THEN 1 ELSE 0 END");pa.append(keyword.lower())
 if not score:out={'items':[]}
 else:
  sql='WITH scored AS ('+SELECT+','+'+'.join(score)+' match_score'+BASE+' WHERE '+where+') SELECT * FROM scored WHERE match_score>0 ORDER BY match_score DESC,quality DESC NULLS LAST,work_id LIMIT 24'
  out={'items':[item(r) for r in q(sql,pa+args)]}
elif route=='neighbors':
 seed=next(iter(rows('w.work_id=%s',[int(P['id'])],1)),None)
 if not seed:out={'items':[]}
 else:
  values=[seed.get('x'),seed.get('y')]+[seed['vad'].get(k) for k in ['v','a','d']]+[seed['lang'].get(k) for k in SHORT]
  expressions=[X,Y]+[num("w.vlm->'affect'->'vad'->>'"+k+"'") for k in ['valence','arousal','dominance']]
  for full in FIELDS:
   expr="w.vlm->'language7'->'"+full+"'"
   expressions.append(num("CASE WHEN jsonb_typeof("+expr+")='object' THEN "+expr+"->>'v' ELSE w.vlm->'language7'->>'"+full+"' END"))
  present=[]
  for expr,value in zip(expressions,values):
   try:
    value=float(value)
    if math.isfinite(value):present.append((expr,value))
   except (TypeError,ValueError):pass
  if not present:out={'items':[]}
  else:
   # Materialize numeric axes once; missing dimensions do not affect RMS denominator.
   axes=','.join(expr.replace("w.vlm->'language7'",'raw.lang').replace("w.vlm->'worldview'",'raw.wv').replace("w.vlm->'affect'",'raw.af')+' AS axis'+str(i) for i,(expr,_) in enumerate(present))
   numerator='+'.join('COALESCE(power(axis'+str(i)+'-%s,2),0)' for i in range(len(present)))
   denominator='+'.join('CASE WHEN axis'+str(i)+' IS NULL THEN 0 ELSE 1 END' for i in range(len(present)))
   exclude=list(set(json.loads(P.get('exclude','[]'))+[int(P['id'])]))
   sql="WITH raw AS MATERIALIZED (SELECT w.work_id,w.quality,w.vlm->'language7' lang,w.vlm->'worldview' wv,w.vlm->'affect' af"+BASE+' WHERE '+where+' AND NOT(w.work_id=ANY(%s))), axes AS MATERIALIZED (SELECT raw.work_id,raw.quality,'+axes+' FROM raw), ranked AS (SELECT *,sqrt(('+numerator+')/NULLIF(('+denominator+'),0)) distance FROM axes) SELECT * FROM ranked WHERE distance IS NOT NULL ORDER BY distance,quality DESC NULLS LAST,work_id LIMIT 18'
   result=q(sql,args+[exclude]+[value for _,value in present]);details={r['work_id']:r for r in rows('w.work_id=ANY(%s)',[[r['work_id'] for r in result]],18)};out={'items':[dict(details[r['work_id']],distance=r['distance']) for r in result if r['work_id'] in details]}
elif route=='intent':
 intent=json.loads(P['intent']);score=[];pa=[]
 if intent.get('wv'):score.append('CASE WHEN '+WV+'=ANY(%s) THEN 1.0 ELSE 0 END');pa.append(intent['wv'])
 if intent.get('emo'):score.append("CASE WHEN w.vlm->'affect'->>'primary_anchor'=ANY(%s) THEN 0.7 ELSE 0 END");pa.append(intent['emo'])
 for key,axis in [('tv','valence'),('ta','arousal')]:
  if intent.get(key) is not None:
   score.append("COALESCE((1-abs("+num("w.vlm->'affect'->'vad'->>'"+axis+"'")+"-%s))*0.7,0)");pa.append(float(intent[key]))
 scoring='+'.join(score) or '0'
 # Rank all eligible works, enforce artist diversity before top-eight selection.
 sql='WITH scored AS MATERIALIZED ('+SELECT+','+scoring+' AS match_score'+BASE+' WHERE '+where+'), ranked AS (SELECT *,row_number() OVER (PARTITION BY artist ORDER BY match_score DESC,quality DESC NULLS LAST,work_id) artist_rank FROM scored) SELECT * FROM ranked WHERE artist_rank<=2 ORDER BY match_score DESC,quality DESC NULLS LAST,work_id LIMIT 8'
 out={'items':[item(r) for r in q(sql,pa+args)]}
elif route=='rule-summary':
 count=q('SELECT count(*) n'+BASE+' WHERE '+where,args)[0]['n']
 out={'count':min(count,cap) if cap else count,'cover':next(iter(rows(where,args,1)),None)}
elif route=='summary':
 sections=q('SELECT '+WV+' key,count(*) count,avg('+X+') x,avg('+Y+') y'+BASE+' WHERE '+where+' GROUP BY 1',args)
 for r in sections:r['items']=rows(where+' AND '+WV+'=%s',args+[r['key']],3)
 out={'total':sum(r['count'] for r in sections),'sections':sections}
elif route=='averages':out={'regavg':regavg()}
elif route=='item':
 if P.get('id'):
  token=P['id'];cond='w.work_id=%s' if str(token).isdigit() else 'w.accession_code=%s';pa=[int(token) if str(token).isdigit() else token.upper()]
 else:
  path=urlsplit(P.get('file','')).path.lstrip('/');keys=[]
  for _ in range(3):keys.extend([path,path.removeprefix('img/')]);path=unquote(path)
  cond='f.cos_key=ANY(%s)';pa=[list(set(keys))]
 rr=rows(cond,pa,1);out=dict(work=rr[0] if rr else None,related=[],regavg={})
 if rr:
  base=rr[0];out['related']=rows(where+' AND (w.artist_id=%s OR '+WV+'=%s) AND w.work_id<>%s',args+[next(iter(q('SELECT artist_id FROM works WHERE work_id=%s',[base['work_id']])))['artist_id'],base['wv'],base['work_id']],12)
elif route=='_frame-source':
 # Private service-side projection; never exposed as a public HTTP endpoint.
 projection="jsonb_build_object('frame',w.vlm->'frame','style',w.vlm->'style','media',w.vlm->'media','color',w.vlm->'color','subject',w.vlm->'subject') AS vlm"
 def frame_item(r):
  v=r['vlm'] or {};fr=v.get('frame') or {};fr=fr if isinstance(fr,dict) else {};key=r['cos_key']
  file=('/'+key) if key.startswith('img/') else '/img/'+quote(key,safe='/')
  legacy_style=v.get('style');legacy_style=legacy_style.get('流派') if isinstance(legacy_style,dict) else legacy_style
  # Only fields used by frames.js and the management cards cross SSH.
  result=dict(work_id=r['work_id'],file=file,title=r['title'] or '无题',artist=r['artist'],region=r['region'],style=r['style_zh'] or legacy_style,medium=v.get('media'),subject=v.get('subject'),color=v.get('color'),frame_suggest=fr.get('key'),frame_why=fr.get('why'),frame_finish=fr.get('finish'),frame_conf=fr.get('conf'))
  return {k:value for k,value in result.items() if value is not None}
 out={'items':[frame_item(r) for r in q(SELECT.replace('w.vlm',projection)+BASE+' WHERE w.exhibited ORDER BY w.quality DESC NULLS LAST,w.work_id ASC')]}

elif route=='resolve':
 keys=json.loads(P['keys']);ids=[];codes=[];files=[];normal=[]
 for key in keys:
  key=str(key);variants=[]
  if key.isdigit():ids.append(int(key))
  else:
   codes.append(key.upper());path=urlsplit(key).path.lstrip('/')
   for _ in range(3):variants.extend([path,path.removeprefix('img/')]);path=unquote(path)
   files.extend(variants)
  normal.append((key,variants))
 raw=q(SELECT+BASE+' WHERE w.work_id=ANY(%s) OR w.accession_code=ANY(%s) OR f.cos_key=ANY(%s)',[ids,codes,list(set(files))])
 byid={str(r['work_id']):r for r in raw};bycode={r['accession_code']:r for r in raw};byfile={r['cos_key']:r for r in raw}
 found=[];missing=[];matches={}
 for key,variants in normal:
  r=byid.get(key) or bycode.get(key.upper()) or next((byfile[v] for v in variants if v in byfile),None)
  if r:found.append(item(r));matches[key]=r['work_id']
  else:missing.append(key)
 out={'items':found,'missing':missing,'matches':matches}
elif route=='test-pool':
 candidates=rows(where+' AND w.accession_code=ANY(%s)',args+[P.get('_test_codes',[])],120) if P.get('_test_codes') else []
 out={'items':candidates if len(candidates)>=30 else sum([rows(where+' AND '+WV+'=%s',args+['WV'+str(i)],12) for i in range(1,7)],[])}
elif route=='artists-near':
 x=float(P.get('x',0));y=float(P.get('y',0));n=max(1,min(10,int(P.get('limit',3))))
 if not math.isfinite(x+y) or not(0<=x<=1 and 0<=y<=1):raise ValueError('invalid coordinates')
 near=q("SELECT COALESCE(a.aha_kg_id,a.artist_id) id,COALESCE(ac.cn,a.name_cn,a.name_en,'佚名') artist,avg("+X+") x,avg("+Y+") y,count(*) n"+BASE+" WHERE "+where+" GROUP BY 1,2 HAVING count(*)>=2 ORDER BY power(avg("+X+")-%s,2)+power(avg("+Y+")-%s,2) NULLS LAST LIMIT %s",args+[x,y,n])
 for a in near:
  a['rep']=next(iter(rows(where+" AND COALESCE(a.aha_kg_id,a.artist_id)=%s",args+[a['id']],1)),None);a['d']=math.hypot(a['x']-x,a['y']-y)
 out={'items':[a for a in near if a['rep']]}
else:raise ValueError('unsupported endpoint')
print(json.dumps(out,ensure_ascii=False,default=str));c.rollback();c.close()
