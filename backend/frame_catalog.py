"""Server-side bounded snapshot; retain full-catalog frame semantics without browser bulk data."""
import json,time,threading,hashlib,base64,subprocess,urllib.request,os
from pathlib import Path
from collections import OrderedDict
LOCK=threading.Lock();SOURCE=None;SOURCE_AT=0;SOURCE_VERSION=None;SUMMARIES=OrderedDict()
def public_data(path):
 origin=os.environ.get('AHA_PUBLIC_ORIGIN','https://aha.yishujia.art')
 with urllib.request.urlopen(origin+path,timeout=8) as r:
  payload=r.read(4*1024*1024+1)
  if len(payload)>4*1024*1024:raise ValueError('frame configuration exceeds budget')
  return json.loads(payload)
def read_frames(p,query):
 global SOURCE,SOURCE_AT,SOURCE_VERSION
 from backend.client import BadRequest
 if not LOCK.acquire(timeout=45):raise TimeoutError('frame preparation busy')
 try:
  if SOURCE is None or time.monotonic()-SOURCE_AT>300:
   candidate=query({'route':'_frame-source'})['items']
   if len(candidate)>500000:raise ValueError('frame catalog exceeds snapshot budget')
   if len(json.dumps(candidate,ensure_ascii=False).encode())>128*1024*1024:raise ValueError('frame snapshot byte budget exceeded')
   SOURCE=candidate;SOURCE_AT=time.monotonic();SOURCE_VERSION=str(time.time_ns());SUMMARIES.clear()
  # Read current canonical rules on every request so successful saves are reflected.
  canonical=public_data('/api/frames').get('frames',{});styles=public_data('/api/frame_styles').get('styles',[])
  version=hashlib.sha256(json.dumps([SOURCE_VERSION,canonical,styles],sort_keys=True).encode()).hexdigest()[:20]
  computed=SUMMARIES.get(version)
  if computed is None:
   payload=json.dumps({'items':SOURCE,'canonical':canonical,'styles':styles},ensure_ascii=False)
   if len(payload.encode())>128*1024*1024:raise ValueError('frame snapshot byte budget exceeded')
   result=subprocess.run(['node',str(Path(__file__).with_name('frame-snapshot.cjs'))],input=payload,text=True,capture_output=True,timeout=30)
   if result.returncode:raise RuntimeError('frame rules could not be evaluated')
   computed=json.loads(result.stdout);computed['review_ids']=set(computed['review_ids']);SUMMARIES[version]=computed
   while len(SUMMARIES)>2:SUMMARIES.popitem(last=False)
  signature=hashlib.sha256(json.dumps({k:p.get(k) for k in ['q','review','filter']},sort_keys=True).encode()).hexdigest()[:16]
  offset=0;reset=False
  if p.get('cursor'):
   token=json.loads(base64.urlsafe_b64decode(p['cursor']))
   if token['filter']!=signature:raise BadRequest('frame filter changed; restart pagination')
   if token['v']!=version:reset=True
   else:offset=token['offset']
  term=p.get('q','').casefold();review=computed['review_ids']
  selected=[w for w in SOURCE if (not term or term in ((w.get('title') or '')+' '+(w.get('artist') or '')).casefold()) and (p.get('review')!='1' or w['work_id'] in review) and (p.get('filter')!='human' or canonical.get(w['file']))]
  n=int(p.get('limit',40));items=selected[offset:offset+n];more=offset+len(items)<len(selected)
  cursor=base64.urlsafe_b64encode(json.dumps({'v':version,'offset':offset+len(items),'filter':signature}).encode()).decode() if more else None
  return dict(computed['summary'],items=items,has_more=more,next_cursor=cursor,matched_total=len(selected),canonical={w['file']:canonical[w['file']] for w in items if w['file'] in canonical},data_version=version,pagination_reset=reset)
 finally:LOCK.release()
