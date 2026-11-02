import unittest,json,threading,time,tempfile
from pathlib import Path
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from backend import client
import serve
class ServiceLimits(unittest.TestCase):
 def test_new_contract_validation(self):
  invalid=[('intent',{}),('curate-match',{}),('browse',{'rule':'[]'}),('resolve',{'keys':json.dumps(list(range(61)))}),('neighbors',{'id':'not-an-id'}),('browse',{'min_quality':'NaN'}),('intent',{'intent':'{"tv":2}'}),('curate-match',{'match':'{"pick":{"keywords":"oops"}}'}),('rule-summary',{'rule':'{"limit":-1}'})]
  for endpoint,params in invalid:
   with self.assertRaises(client.BadRequest):client.params('/cat/'+endpoint+'?'+urlencode(params))
  self.assertEqual(client.params('/cat/browse?min_quality=0.95')['min_quality'],'0.95')
 def test_failed_singleflight_is_shared(self):
  client.CACHE.clear();calls=[];barrier=threading.Barrier(5)
  def query(_):calls.append(1);time.sleep(.08);raise RuntimeError('unavailable')
  def caller(_):
   barrier.wait()
   try:client.read('/cat/home')
   except RuntimeError:return 'failed'
  with patch.object(client,'_query',query),ThreadPoolExecutor(max_workers=5) as pool:
   self.assertEqual(list(pool.map(caller,range(5))),['failed']*5)
  self.assertEqual(len(calls),1);self.assertFalse(client.INFLIGHT)
 def test_resource_lock_reclaimed_on_failure(self):
  with tempfile.TemporaryDirectory() as root,patch.object(serve,'CACHE',Path(root)),patch.object(serve.urllib.request,'urlopen',side_effect=RuntimeError('failed')):
   with self.assertRaises(RuntimeError):serve.resource('/img/not-real.webp')
   self.assertEqual(serve.LOCKS,{})
 def test_disk_budget_evicts_oldest(self):
  with tempfile.TemporaryDirectory() as root,patch.object(serve,'CACHE',Path(root)),patch.object(serve,'MAX_CACHE_BYTES',4),patch.object(serve,'LAST_PRUNE',float('-inf')):
   Path(root,'first.bin').write_bytes(b'1234');Path(root,'first.json').write_text('{}')
   time.sleep(.01);Path(root,'second.bin').write_bytes(b'5678')
   serve.prune_cache();self.assertFalse(Path(root,'first.bin').exists());self.assertTrue(Path(root,'second.bin').exists())
if __name__=='__main__':unittest.main()
