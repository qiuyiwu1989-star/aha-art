import unittest,json,base64,threading,time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from backend import client
class Backend(unittest.TestCase):
 def setUp(self):client.CACHE.clear()
 def test_validation(self):
  for p in ['/cat/browse?limit=8000','/cat/browse?cursor=broken','/cat/browse?wv=WV7','/cat/item','/cat/home?_special=unsafe']:
   with self.assertRaises(client.BadRequest):client.params(p)
 def test_singleflight_and_capacity(self):
  calls=[]
  def query(p):calls.append(p);time.sleep(.02);return {'items':[1]}
  with patch.object(client,'_query',query):
   with ThreadPoolExecutor(max_workers=4) as pool:r=list(pool.map(client.read,['/cat/home']*4))
   self.assertEqual(len(calls),1);self.assertEqual(r,[{'items':[1]}]*4)
   with patch.object(client,'MAX_CACHE',2):
    client.read('/cat/browse?wv=WV1');client.read('/cat/browse?wv=WV2');self.assertEqual(len(client.CACHE),2)
 def test_failure_not_cached(self):
  with patch.object(client,'_query',side_effect=[RuntimeError('failure'),{'items':[]}]):
   with self.assertRaises(RuntimeError):client.read('/cat/home')
   self.assertEqual(client.read('/cat/home'),{'items':[]});self.assertEqual(client.INFLIGHT,{})
if __name__=='__main__':unittest.main()
