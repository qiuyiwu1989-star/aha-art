"""Bounded deterministic 16-image audit; never fetch originals or enumerate remote assets."""
import json, urllib.request, urllib.error, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
root=Path(__file__).resolve().parents[1]
items=list(json.loads((root/'web/data/live/artworks_index.json').read_text())['artworks'].values())
sample=[items[i*len(items)//16] for i in range(16)]
def check(a):
 t=time.monotonic(); result={'slug':a['slug']}
 try:
  with urllib.request.urlopen(a['thumb'],timeout=15) as r:
   body=r.read(1024*1024+1);mime=r.headers.get('Content-Type','');result.update(status=r.status,mime=mime,bytes=len(body))
   magic=body[:4]==b'RIFF' and body[8:12]==b'WEBP' or body[:3]==b'\xff\xd8\xff' or body[:8]==b'\x89PNG\r\n\x1a\n'
   result['category']='image_signature_ok' if magic else 'non_image_or_unsupported'
   if len(body)>1024*1024:result['category']='over_1MiB'
 except urllib.error.HTTPError as e:result.update(status=e.code,category='http_error')
 except Exception as e:result.update(category='network_or_timeout',error=type(e).__name__)
 result['seconds']=round(time.monotonic()-t,3);return result
with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(check,sample))
(root/'tests/image-health-sample.json').write_text(json.dumps({'scope':'16 evenly spaced catalog thumbnails; max concurrency 2; 15s timeout; signature only, no browser decode assertion','results':results},indent=2))
print(json.dumps(results))
