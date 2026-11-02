import unittest,json,base64
from unittest.mock import patch
from types import SimpleNamespace
from backend import frame_catalog as f
class FrameCatalog(unittest.TestCase):
 def setUp(self):
  f.SOURCE=None;f.SUMMARIES.clear()
  self.items=[dict(work_id=i,file=str(i),title='Moon' if i%2 else 'Sun',artist='Painter') for i in range(1,6)]
  self.canonical={'2':'gilt'}
 def public(self,path):return {'frames':self.canonical} if path.endswith('/frames') else {'styles':[]}
 def snapshot(self,*a,**kw):return SimpleNamespace(returncode=0,stdout=json.dumps({'summary':{'total':5,'human_count':1,'review_count':4,'stats':{}},'review_ids':[1,3,4,5]}))
 def read(self,**p):return f.read_frames({'limit':2,**p},lambda p:{'items':self.items})
 def test_page_filter_and_full_counts(self):
  with patch.object(f,'public_data',self.public),patch.object(f.subprocess,'run',self.snapshot):
   first=self.read();second=self.read(cursor=first['next_cursor']);self.assertEqual([x['work_id'] for x in second['items']],[3,4]);self.assertEqual(second['total'],5)
   review=self.read(review='1',q='Moon');self.assertEqual(review['matched_total'],3)
   human=self.read(filter='human');self.assertEqual(human['canonical'],{'2':'gilt'});self.assertEqual(human['total'],5)
 def test_expired_cursor_restarts_with_explicit_replacement(self):
  with patch.object(f,'public_data',self.public),patch.object(f.subprocess,'run',self.snapshot):
   first=self.read();self.canonical['3']='wood';new=self.read(cursor=first['next_cursor']);self.assertTrue(new['pagination_reset']);self.assertEqual(new['items'],first['items']);self.assertNotEqual(first['data_version'],new['data_version'])
   nextpage=self.read(cursor=new['next_cursor']);self.assertFalse(nextpage['pagination_reset']);self.assertEqual(nextpage['items'][0]['work_id'],3)
if __name__=='__main__':unittest.main()
