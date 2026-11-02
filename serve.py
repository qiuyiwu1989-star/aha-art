# coding: utf-8
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import urllib.request, urllib.parse, urllib.error, json, hashlib, time, threading, gzip
from collections import OrderedDict
CACHE=Path(__file__).parent/".cache"
CACHE.mkdir(exist_ok=True)
# Per-key locks exist only while readers are active; image traffic cannot starve APIs.
LOCKS={}
LOCK_GUARD=threading.Lock()
API_SLOTS=threading.BoundedSemaphore(3)
IMAGE_SLOTS=threading.BoundedSemaphore(5)
MAX_CACHE_BYTES=512*1024*1024
PRUNE_LOCK=threading.Lock()
LAST_PRUNE=float('-inf')
def prune_cache():
 global LAST_PRUNE
 if time.monotonic()-LAST_PRUNE<60 or not PRUNE_LOCK.acquire(blocking=False):return
 try:
  LAST_PRUNE=time.monotonic();entries=[]
  for f in CACHE.glob('*.bin'):
   try:st=f.stat();entries.append((st.st_mtime,st.st_size,f))
   except FileNotFoundError:pass
  total=sum(e[1] for e in entries)
  for modified,size,f in sorted(entries):
   if total<=MAX_CACHE_BYTES and time.time()-modified<86400:continue
   key=f.stem
   with LOCK_GUARD:
    if key in LOCKS:continue
    f.unlink(missing_ok=True);f.with_suffix('.json').unlink(missing_ok=True)
   total-=size
 finally:PRUNE_LOCK.release()
def resource(path):
 key=hashlib.sha256(path.encode()).hexdigest()
 with LOCK_GUARD:
  entry=LOCKS.setdefault(key,[threading.Lock(),0]);entry[1]+=1
 try:
  if not entry[0].acquire(timeout=18):raise TimeoutError('resource wait expired')
  try:
   datafile=CACHE/(key+'.bin');meta=CACHE/(key+'.json')
   image=path.startswith(('/img/','/cimg/'));ttl=86400 if image else 120
   if meta.exists() and datafile.exists() and time.time()-meta.stat().st_mtime<ttl:
    return datafile.read_bytes(),json.loads(meta.read_text())['type'],ttl
   slots=IMAGE_SLOTS if image else API_SLOTS
   if not slots.acquire(timeout=3):raise TimeoutError('resource queue full')
   try:
    req=urllib.request.Request(UPSTREAM+path,headers={'User-Agent':'AHA-local-preview'})
    with urllib.request.urlopen(req,timeout=12) as r:
     data=r.read(20*1024*1024+1);kind=r.headers.get('Content-Type','application/octet-stream')
     if len(data)>20*1024*1024:raise ValueError('resource too large')
     if image and not kind.startswith('image/'):raise ValueError('invalid image')
   finally:slots.release()
   datafile.write_bytes(data);meta.write_text(json.dumps({'type':kind}))
   return data,kind,ttl
  finally:entry[0].release()
 finally:
  with LOCK_GUARD:
   entry[1]-=1
   if not entry[1]:LOCKS.pop(key,None)
  prune_cache()
STATIC_CACHE=OrderedDict()
STATIC_LOCK=threading.Lock()
ROOT=Path(__file__).parent/'web'
UPSTREAM='https://aha.yishujia.art'
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*a,**kw):super().__init__(*a,directory=str(ROOT),**kw)
 def reply(self,status,obj):
  body=json.dumps(obj,ensure_ascii=False).encode();compressed='gzip' in self.headers.get('Accept-Encoding','');body=gzip.compress(body) if compressed else body;self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Vary','Accept-Encoding');
  if hasattr(self,'catalog_started'):self.send_header('Server-Timing','catalog;dur='+str(round((time.monotonic()-self.catalog_started)*1000,1)))
  if compressed:self.send_header('Content-Encoding','gzip')
  self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def do_POST(self):self.reply(403,{'error':'本机只读预览：保存、登录和生成未连接生产环境'})
 do_PUT=do_POST
 do_DELETE=do_POST
 do_PATCH=do_POST
 def do_GET(self):
  p=urllib.parse.urlsplit(self.path).path
  if p in ['/cat/home','/cat/browse','/cat/item','/cat/test-pool','/cat/artists-near','/cat/summary','/cat/averages','/cat/resolve','/cat/rule-summary','/cat/intent','/cat/catalog-facets','/cat/curate-match','/cat/neighbors','/cat/frame-catalog']:
   try:
    from backend.client import read, BadRequest
    self.catalog_started=time.monotonic()
    return self.reply(200,read(self.path))
   except BadRequest:return self.reply(400,{'error':'查询参数无效'})
   except Exception:return self.reply(502,{'error':'只读数据服务暂不可用，请重试'})
  if p=='/':self.path='/museum.html';p='/museum.html'
  if p=='/api/me/state':return self.reply(200,{'collections':[],'ratings':{},'taste':None})
  if p.startswith('/api/me/'):return self.reply(200,{'ready':False,'items':[],'logged_in':False})
  if p.startswith('/api/') and p not in ['/api/hot','/api/personas','/api/specials','/api/frames','/api/frame_styles']:
   return self.reply(403,{'error':'此接口未在只读预览启用'})
  allowed=['/cat/healthz','/cat/exhibit','/cat/exhibitions','/cat/facets','/cat/works','/cat/styles','/cat/artists_canon','/cat/artist','/cat/measured_atlas']
  if p.startswith('/cat/') and p not in allowed and not p.startswith(('/cat/work/','/cat/related/')):
   return self.reply(403,{'error':'此接口未在只读预览启用'})
  if p.startswith(('/cat/','/api/','/img/','/cimg/')):
   try:
    data,kind,ttl=resource(self.path)
    compressed='gzip' in self.headers.get('Accept-Encoding','') and ('json' in kind or 'text' in kind)
    if compressed:data=gzip.compress(data)
    self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Cache-Control','private, max-age='+str(ttl));self.send_header('Vary','Accept-Encoding')
    if compressed:self.send_header('Content-Encoding','gzip')
    self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
   except (BrokenPipeError,ConnectionResetError):pass
   except Exception:self.reply(502,{'error':'远端只读资源暂不可用'})
   return
  if 'gzip' in self.headers.get('Accept-Encoding','') and Path(p).suffix in ('.json','.js','.css','.html'):
   target=Path(self.translate_path(self.path)).resolve()
   if target.is_file() and target.is_relative_to(ROOT.resolve()):
    st=target.stat();key=(str(target),st.st_mtime_ns,st.st_size)
    with STATIC_LOCK:
     data=STATIC_CACHE.get(key)
     if data is None:
      data=gzip.compress(target.read_bytes(),compresslevel=6);STATIC_CACHE[key]=data
     STATIC_CACHE.move_to_end(key)
     while len(STATIC_CACHE)>16 or sum(len(x) for x in STATIC_CACHE.values())>32*1024*1024:STATIC_CACHE.popitem(last=False)
    etag='"'+hashlib.sha256(repr(key).encode()).hexdigest()[:20]+'"'
    if self.headers.get('If-None-Match')==etag:
     self.send_response(304);self.send_header('ETag',etag);self.send_header('Vary','Accept-Encoding');self.end_headers();return
    self.send_response(200);self.send_header('Content-Type',self.guess_type(str(target)));self.send_header('Content-Encoding','gzip');self.send_header('Vary','Accept-Encoding');self.send_header('ETag',etag);self.send_header('Cache-Control','public, max-age=0, must-revalidate');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
  return super().do_GET()
 def log_message(self,*a):pass
if __name__=='__main__':
 print('AHA performance preview: http://127.0.0.1:8766',flush=True)
 ThreadingHTTPServer(('127.0.0.1',8766),Handler).serve_forever()
