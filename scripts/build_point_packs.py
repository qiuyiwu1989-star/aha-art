"""Lossless dictionary/column packs; deterministic generation from authoritative JSON."""
from pathlib import Path
import json,os
root=Path(__file__).resolve().parents[1]/'web/data/live'
for name in ['points','affect']:
 source=json.loads((root/f'{name}.json').read_text());rows=source['points'];keys=list(dict.fromkeys(k for row in rows for k in row));columns=[]
 for k in keys:
  values=[r.get(k) for r in rows]
  unique=list(dict.fromkeys(v for v in values if isinstance(v,str)))
  lookup={v:i for i,v in enumerate(unique)}
  # Dictionary encode only repeated strings. Avoid collisions with actual numeric values.
  if all(isinstance(v,str) for v in values) and len(os.path.commonprefix(values))>30:
   prefix=os.path.commonprefix(values);columns.append({'prefix':prefix,'values':[v[len(prefix):] for v in values]})
  elif all(isinstance(v,str) for v in values) and len(unique)<len(values)//2:
   columns.append({'dictionary':unique,'values':[lookup[v] for v in values]})
  else:columns.append({'values':values})
 # Preserve absent keys separately from explicit nulls.
 pack={'version':1,'header':{k:v for k,v in source.items() if k!='points'},'keys':keys,'columns':columns,'present':[[i for i,k in enumerate(keys) if k in r] for r in rows]}
 (root/f'{name}.pack.json').write_text(json.dumps(pack,ensure_ascii=False,separators=(',',':')))
 print(name,(root/f'{name}.pack.json').stat().st_size)
