"""Serial local preview integration checks; no writes or production load tests."""
import urllib.request,urllib.parse,json,time,gzip
from pathlib import Path
base='http://127.0.0.1:8766'
results=[]
def get(route,params=None):
 start=time.monotonic();url=base+route+('?' + urllib.parse.urlencode(params) if params else '')
 with urllib.request.urlopen(urllib.request.Request(url,headers={'Accept-Encoding':'gzip'}),timeout=50) as r:
  body=r.read();size=len(body)
  if r.headers.get('Content-Encoding')=='gzip':body=gzip.decompress(body)
  data=json.loads(body);results.append({'route':route,'seconds':round(time.monotonic()-start,3),'bytes':size,'status':r.status})
 return data
home=get('/cat/home');assert len(home['items'])==24
page=get('/cat/browse',{'cursor':home['next_cursor'],'limit':24});assert not set(w['work_id'] for w in home['items'])&set(w['work_id'] for w in page['items'])
w=home['items'][0];resolved=get('/cat/resolve',{'keys':json.dumps([w['work_id'],w['file'],'missing-test-key'])});assert len(resolved['items'])==2 and resolved['missing']==['missing-test-key']
facets=get('/cat/catalog-facets');assert set(facets['facets'])=={'style','subject','emo','wv'}
summary=get('/cat/rule-summary',{'rule':json.dumps({'wv':['WV3'],'limit':24})});assert summary['count']==24 and summary['cover']['wv']=='WV3'
intent=get('/cat/intent',{'intent':json.dumps({'wv':['WV3'],'ta':.2})});assert len(intent['items'])==8
from collections import Counter
assert max(Counter(x['artist'] for x in intent['items']).values())<=2
matched=get('/cat/curate-match',{'match':json.dumps({'themes':['光'],'constraints':[{'vgt':.6}]})});assert 0<len(matched['items'])<=24
neighbors=get('/cat/neighbors',{'id':208445});assert len(neighbors['items'])==18 and 208445 not in [x['work_id'] for x in neighbors['items']]
assert all(a['distance']<=b['distance'] for a,b in zip(neighbors['items'],neighbors['items'][1:]))
quality=get('/cat/browse',{'min_quality':.95,'limit':2});assert all(x['quality']>=.95 for x in quality['items'])
for name in ['points','affect']:
 packed=get('/data/live/'+name+'.pack.json');assert packed
Path('tests/catalog-http.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
