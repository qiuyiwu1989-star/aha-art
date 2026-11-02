"""Local-only derivative preparation. No network, upload or database write."""
import argparse,json,hashlib
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--work-id',type=int,required=True);p.add_argument('--source',type=Path,required=True)
p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--apply',action='store_true')
p.add_argument('--max-source-bytes',type=int,default=128*1024*1024)
p.add_argument('--max-pixels',type=int,default=100_000_000)
a=p.parse_args()
if a.work_id<1:raise SystemExit('Invalid work ID')
source=a.source.resolve();out=a.output_dir.resolve()
if not source.is_file():raise SystemExit('Source must be an existing local file; no downloads performed')
if source.stat().st_size>a.max_source_bytes:raise SystemExit('Source byte budget exceeded')
plan={'work_id':a.work_id,'source':str(source),'output':str(out/f'{a.work_id}.webp'),'edge':720,'max_output_bytes':512*1024,'mode':'apply' if a.apply else 'dry-run'}
print(json.dumps(plan,ensure_ascii=False,indent=2))
if not a.apply:raise SystemExit(0)
# Pillow is optional until explicitly executing. Treat decompression warnings as errors.
from PIL import Image,ImageOps
import warnings,io
Image.MAX_IMAGE_PIXELS=a.max_pixels
warnings.simplefilter('error',Image.DecompressionBombWarning)
with Image.open(source) as im:
 if im.width*im.height>a.max_pixels:raise SystemExit('Source pixel budget exceeded')
 im.draft('RGB',(720,720));im=ImageOps.exif_transpose(im);im.thumbnail((720,720))
 if im.mode not in ('RGB','RGBA'):im=im.convert('RGB')
 payload=io.BytesIO();im.save(payload,format='WEBP',quality=82,method=6);blob=payload.getvalue()
 if len(blob)>512*1024:raise SystemExit('Output byte budget exceeded; nothing written')
 out.mkdir(parents=True,exist_ok=True)
 target=out/f'{a.work_id}.webp'
 with target.open('xb') as f:f.write(blob)
 manifest={'work_id':a.work_id,'local_derivative':str(target),'width':im.width,'height':im.height,'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest(),'publication_status':'not_uploaded','database_status':'not_updated'}
 with (out/f'{a.work_id}.manifest.json').open('x') as f:json.dump(manifest,f,ensure_ascii=False,indent=2)
print(json.dumps(manifest,ensure_ascii=False))
