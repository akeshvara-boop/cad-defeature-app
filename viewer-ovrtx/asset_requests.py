"""Validate the trusted host API's requests before the render thread sees them."""
from pathlib import Path
import re


def validate_asset(value, root):
    if not root:
        raise ValueError('Asset loading is not configured')
    wid, aid = value.get('workflow_id',''), value.get('asset_id','')
    if not re.fullmatch('[0-9a-f]{12}',wid) or not re.fullmatch('[0-9a-f]{32}',aid):
        raise ValueError('Invalid workflow or asset id')
    allowed = Path(root).expanduser().resolve()
    path = Path(value.get('stage','')).resolve(strict=True)
    expected = allowed/wid/aid/'asset'/'review.usda'
    if path != expected or not path.is_file():
        raise ValueError('Stage is outside this workflow review directory')
    sha = value.get('source_sha256','')
    if not re.fullmatch('[0-9a-f]{64}',sha):
        raise ValueError('Invalid source hash')
    return dict(stage=str(path),workflow_id=wid,asset_id=aid,source_sha256=sha)
