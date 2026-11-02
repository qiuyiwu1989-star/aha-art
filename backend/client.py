# coding: utf-8
import subprocess,json,threading,time,base64,urllib.request
from collections import OrderedDict
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
SLOTS=threading.BoundedSemaphore(3)
LOCK=threading.Lock();CACHE=OrderedDict();INFLIGHT={};MAX_CACHE=128
ALLOWED={'home','summary','averages','browse','item','test-pool','artists-near','resolve','rule-summary','intent','catalog-facets','curate-match','neighbors','frame-catalog'}
class BadRequest(ValueError):pass
def params(path):
 u=urlsplit(path);p={k:v[-1] for k,v in parse_qs(u.query).items()};p['route']=u.path.rsplit('/',1)[-1]
 if p['route'] not in ALLOWED:raise BadRequest('unknown endpoint')
 if set(p)-{'route','limit','cursor','collection','wv','emo','artist','special','id','file','x','y','keys','q','region','style','rule','min_quality','intent','match','exclude','subject','style_name','review','filter'}:raise BadRequest('unknown parameters')
 if any(len(v)>12000 for v in p.values()):raise BadRequest('parameter too long')
 try:
  if 'limit' in p and not 1<=int(p['limit'])<=60:raise ValueError()
  if 'collection' in p and int(p['collection'])<1:raise ValueError()
  if 'wv' in p and p['wv'] not in ['WV'+str(i) for i in range(1,7)]:raise ValueError()
  if p.get('review') not in (None,'0','1'):raise ValueError()
  if p.get('filter') not in (None,'human'):raise ValueError()
  if p.get('cursor') and p['route']=='frame-catalog':
   token=json.loads(base64.urlsafe_b64decode(p['cursor']))
   if not isinstance(token,dict) or set(token)!={'v','offset','filter'} or not isinstance(token['offset'],int) or token['offset']<0:raise ValueError()
  if p.get('cursor') and p['route']!='frame-catalog':
   token=json.loads(base64.urlsafe_b64decode(p['cursor']))
   if not isinstance(token,dict) or not {'q','id','pos','filter'}<=set(token):raise ValueError()
   if int(token['pos'])<0 or int(token['id'])<1:raise ValueError()
  if 'min_quality' in p and not 0<=float(p['min_quality'])<=1:raise ValueError()
  if p['route']=='neighbors':
   if not p.get('id','').isdigit():raise ValueError()
   excluded=json.loads(p.get('exclude','[]'))
   if not isinstance(excluded,list) or len(excluded)>60 or any(not isinstance(x,int) for x in excluded):raise ValueError()
  if p['route']=='curate-match':
   if 'match' not in p:raise ValueError()
   match=json.loads(p.get('match','{}'))
   if not isinstance(match,dict) or set(match)-{'themes','constraints','east','west','pick'}:raise ValueError()
   arrays=[match.get('themes',[])];pick=match.get('pick',{})
   if not isinstance(pick,dict) or set(pick)-{'styles','subjects','emotions','keywords'}:raise ValueError()
   arrays.extend(pick.values())
   if any(not isinstance(a,list) or len(a)>30 or any(not isinstance(x,str) or len(x)>100 for x in a) for a in arrays):raise ValueError()
   constraints=match.get('constraints',[])
   if not isinstance(constraints,list) or len(constraints)>20:raise ValueError()
   for constraint in constraints:
    if not isinstance(constraint,dict) or set(constraint)-{'vlt','vgt','aLt','agt','region'}:raise ValueError()
    for key,val in constraint.items():
     if key=='region':
      if val not in ('east','west'):raise ValueError()
     elif not 0<=float(val)<=1:raise ValueError()
  if p['route']=='intent':
   if 'intent' not in p:raise ValueError()
   intent=json.loads(p.get('intent','{}'))
   if not isinstance(intent,dict) or set(intent)-{'wv','emo','tv','ta','hit'}:raise ValueError()
   for k in ('wv','emo'):
    if not isinstance(intent.get(k,[]),list) or len(intent.get(k,[]))>30 or any(not isinstance(x,str) or len(x)>100 for x in intent.get(k,[])):raise ValueError()
   for k in ('tv','ta'):
    if intent.get(k) is not None and not 0<=float(intent[k])<=1:raise ValueError()
  if 'rule' in p or p['route']=='rule-summary':
   rule=json.loads(p.get('rule','{}'))
   if not isinstance(rule,dict) or set(rule)-{'emo','wv','region','limit'}:raise ValueError()
   for k in ('emo','wv'):
    if k in rule and (not isinstance(rule[k],list) or len(rule[k])>30 or any(not isinstance(x,str) or len(x)>100 for x in rule[k])):raise ValueError()
   if rule.get('limit') is not None and (not isinstance(rule['limit'],int) or not 1<=rule['limit']<=100000):raise ValueError()
   if rule.get('region') and rule['region'] not in ('east','west'):raise ValueError()
  if 'q' in p and len(p['q'])>200:raise ValueError()
  if 'style' in p and not p['style'].isdigit():raise ValueError()
  if p['route']=='resolve':
   keys=json.loads(p.get('keys','[]'))
   if not isinstance(keys,list) or not 1<=len(keys)<=60 or any(not isinstance(k,(str,int)) or isinstance(k,bool) or len(str(k))>1024 for k in keys):raise ValueError()
  if p['route']=='item' and not (p.get('id') or p.get('file')):raise ValueError()
 except Exception as e:raise BadRequest('invalid parameters') from e
 return p

def _query(p):
 if p['route']=='test-pool':
  album=Path(__file__).parent.parent/'web/data/test_album.json'
  if album.exists():
   d=json.loads(album.read_text());values=d.get('items',d.get('codes',[]));p['_test_codes']=[str(x.get('code','')) if isinstance(x,dict) else str(x) for x in values][:120]
 if p.get('special'):
  with urllib.request.urlopen('https://aha.yishujia.art/api/specials',timeout=8) as response:sp=json.load(response)
  found=next((s for s in sp.get('items',[]) if str(s.get('id'))==p['special'] and s.get('public') is not False),None)
  if not found:raise BadRequest('unknown special')
  p['_special']={k:found.get(k) for k in ('rule','work_ids')}
 script='REQUEST='+repr(p)+'\n'+Path(__file__).with_name('remote_read.py').read_text()
 if not SLOTS.acquire(timeout=5):raise TimeoutError('read queue full')
 try:
  r=subprocess.run(['ssh']+(['-C'] if p['route']=='_frame-source' else [])+['-o','BatchMode=yes','-o','ConnectTimeout=5','deepbrain','python3 -'],input=script,text=True,capture_output=True,timeout=35)
 finally:SLOTS.release()
 if r.returncode:
  if 'ValueError:' in r.stderr or 'cursor filter mismatch' in r.stderr:raise BadRequest('invalid query or cursor')
  raise RuntimeError('Read-only database query failed')
 return json.loads(r.stdout)

def read(path):
 p=params(path)
 if p['route']=='frame-catalog':
  from backend.frame_catalog import read_frames
  return read_frames(p,_query)
 key=json.dumps(p,sort_keys=True);ttl=300 if p['route'] in ('summary','averages','test-pool','catalog-facets','rule-summary') else 120
 while True:
  with LOCK:
   hit=CACHE.get(key)
   if hit and time.monotonic()-hit[0]<ttl:CACHE.move_to_end(key);return hit[1]
   wait=INFLIGHT.get(key)
   if wait is None:wait=INFLIGHT[key]={'event':threading.Event(),'error':None,'data':None};owner=True
   else:owner=False
  if owner:break
  if not wait['event'].wait(50):raise TimeoutError('shared read timeout')
  if wait['error'] is not None:raise wait['error']
  return wait['data']
 try:
  data=_query(p);wait['data']=data
  with LOCK:
   CACHE[key]=(time.monotonic(),data);CACHE.move_to_end(key)
   while len(CACHE)>MAX_CACHE:CACHE.popitem(last=False)
  return data
 except Exception as error:
  wait['error']=error;raise
 finally:
  with LOCK:INFLIGHT.pop(key,None);wait['event'].set()
