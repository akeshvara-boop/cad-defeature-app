from pathlib import Path
import tempfile
import unittest
from asset_requests import validate_asset


class AssetTests(unittest.TestCase):
    def test_scoped_stage(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);wid='abcdef123456';aid='a'*32
            stage=root/wid/aid/'asset'/'review.usda'
            stage.parent.mkdir(parents=True);stage.write_text('#usda 1.0')
            value=dict(stage=str(stage),workflow_id=wid,asset_id=aid,source_sha256='b'*64)
            self.assertEqual(validate_asset(value,root)['workflow_id'],wid)
            value['workflow_id']='111111111111'
            with self.assertRaises(ValueError):validate_asset(value,root)

    def test_unconfigured_loader(self):
        with self.assertRaises(ValueError):validate_asset({},None)
