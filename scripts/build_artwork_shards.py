"""Deterministic, lossless detail shards; rerun when source dataset changes."""
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]/'web/data/live'
data=json.loads((root/'artworks_v2.json').read_text())['artworks']
shards=[{} for _ in range(64)]
for slug,record in data.items():
    # Match JS UTF-16 charCodeAt, including non-BMP slugs.
    raw=slug.encode('utf-16-le'); h=0
    for i in range(0,len(raw),2): h=(h*31+int.from_bytes(raw[i:i+2],'little'))&0xffffffff
    shards[h%64][slug]=record
out=root/'artwork-details';out.mkdir(exist_ok=True)
for i, shard in enumerate(shards): (out/f'{i}.json').write_text(json.dumps(shard,ensure_ascii=False,separators=(',',':')))
assert {k:v for shard in shards for k,v in shard.items()}==data
print(f'Verified lossless sharding: {len(data)} records, 64 shards')
