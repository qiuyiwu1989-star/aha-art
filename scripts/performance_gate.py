"""Static regression guard. Existing debt is explicit; this is not runtime/Lighthouse proof."""
from pathlib import Path
import re,json,sys
ROOT=Path(__file__).resolve().parents[1]
# These workflows need complete data contracts, not truncated pages.
EXCEPTIONS={}
PACKAGE_BUDGETS={'web/data/live/points.pack.json':5276016,'web/data/live/affect.pack.json':5039303,'web/data/live/artworks_v2.json':12467108,'web/data/live/points.json':8351942,'web/data/live/affect.json':7877182,'web/data/live/artworks_index.json':1421218}
PATTERN=re.compile(r'limit\s*(?:=|:)\s*[\"\x27]?\s*(?:2000|[5-9]\d{3}|\d{5,})\b')
def scan(root):
 hits={}
 for p in (root/'web').rglob('*'):
  if p.suffix not in ('.html','.js'):continue
  matches=[i for i,line in enumerate(p.read_text(errors='replace').splitlines(),1) if PATTERN.search(line)]
  if matches:hits[str(p.relative_to(root))]=matches
 return hits
def main():
 hits=scan(ROOT)
 violations={p:lines for p,lines in hits.items() if len(lines)>EXCEPTIONS.get(p,0)}
 large=sorted([{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size} for p in (ROOT/'web/data').rglob('*.json') if p.stat().st_size>1024*1024],key=lambda x:-x['bytes'])
 package_violations=[x for x in large if x['bytes']>PACKAGE_BUDGETS.get(x['path'],1024*1024)]
 print(json.dumps({'package_violations':package_violations,'large_request_debt':hits,'new_violations':violations,'static_packages_over_1MiB':large},ensure_ascii=False,indent=2))
 return bool(violations or package_violations)
if __name__=='__main__':sys.exit(main())
