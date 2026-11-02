"""Bounded serial read-only EXPLAIN ANALYZE; no DDL or load generation."""
from pathlib import Path
import subprocess,json
prefix=Path('backend/remote_read.py').read_text().split("route=P['route']")[0]
script="REQUEST={'route':'browse'}\n"+prefix+'''
results=[]
for name,sql,params in [
 ('browse',SELECT+BASE+' WHERE '+where+' ORDER BY w.quality DESC NULLS LAST,w.work_id ASC LIMIT %s',[25]),
 ('resolve',SELECT+BASE+' WHERE w.work_id=ANY(%s)',[[208445]])
]:
 plan=q('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+sql,params)[0]['QUERY PLAN'][0]
 def walk(node):
  return [{'node':node['Node Type'],'rows':node.get('Actual Rows'),'loops':node.get('Actual Loops'),'shared_hit':node.get('Shared Hit Blocks'),'shared_read':node.get('Shared Read Blocks')}] + sum([walk(n) for n in node.get('Plans',[])],[])
 results.append({'query':name,'execution_ms':plan['Execution Time'],'planning_ms':plan['Planning Time'],'nodes':walk(plan['Plan'])})
print(json.dumps(results));c.rollback();c.close()
'''
r=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5','deepbrain','python3 -'],input=script,text=True,capture_output=True,timeout=30)
if r.returncode:raise SystemExit('Read-only query probe failed; no remote mutations performed')
result={'scope':'122 existing database, serial warm/cold state uncontrolled, not public API capacity','queries':json.loads(r.stdout)}
Path('tests/query-evidence.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
