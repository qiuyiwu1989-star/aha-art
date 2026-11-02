import unittest
from types import SimpleNamespace
from unittest.mock import patch
from backend import client,frame_catalog
class FrameTransport(unittest.TestCase):
 def test_compression_private_only(self):
  with patch.object(client.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='{}')) as run:
   client._query({'route':'_frame-source'});self.assertIn('-C',run.call_args.args[0])
   client._query({'route':'home'});self.assertNotIn('-C',run.call_args.args[0])
  with self.assertRaises(client.BadRequest):client.params('/cat/_frame-source')
 def test_over_budget_source_not_published(self):
  old=frame_catalog.SOURCE;oldat=frame_catalog.SOURCE_AT
  try:
   frame_catalog.SOURCE=None
   class Oversize(list):
    def __len__(self):return 500001
   with self.assertRaises(ValueError):frame_catalog.read_frames({},lambda _: {'items':Oversize()})
   self.assertIsNone(frame_catalog.SOURCE)
  finally:frame_catalog.SOURCE=old;frame_catalog.SOURCE_AT=oldat
