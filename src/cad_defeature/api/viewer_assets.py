"""Prepare only a selected workflow's successful CAD output for visual review."""
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
from uuid import uuid4
from urllib.request import Request, urlopen


def output_for(state):
    workflow_id = state['workflow_id']
    healing = state.get('healing') or {}
    if healing.get('status') != 'complete':
        raise ValueError('This workflow has no successful healed CAD output. Complete healing first.')
    active = PurePosixPath(state.get('active_model', ''))
    root = PurePosixPath('/sandbox/ui/runs') / workflow_id
    if '..' in active.parts or root not in active.parents or active.suffix.lower() not in {'.brep', '.step', '.stp', '.iges', '.igs', '.brp'}:
        raise ValueError('CAD output is not owned by the selected workflow.')
    return str(active)


def prepare_review(service, workflow_id, meters_per_unit, up_axis):
    state = service.get(workflow_id)
    source = output_for(state)
    root = Path(os.environ['CAD_UI_REVIEW_ROOT']).expanduser().resolve()
    worker = os.environ['CAD_UI_REVIEW_PYTHON']
    script = Path(__file__).resolve().parents[3] / 'viewer-ovrtx' / 'prepare_cad.py'
    job = root / workflow_id / uuid4().hex
    job.mkdir(parents=True, exist_ok=False)
    cad = job / ('input' + PurePosixPath(source).suffix)
    service.runner._host_command([service.runner.binary, service.runner.sandbox, 'download', source, str(cad)], timeout=600)
    env = os.environ.copy()
    env['PYTHONPATH'] = str(Path(__file__).resolve().parents[2])
    result = subprocess.run([worker, str(script), '--input', str(cad), '--output-dir', str(job/'asset'),
                             '--meters-per-unit', str(meters_per_unit), '--up-axis', up_axis],
                            env=env, capture_output=True, text=True, timeout=600)
    if result.returncode:
        raise RuntimeError('CAD review preparation failed: ' + result.stderr[-1500:])
    manifest = json.loads((job/'asset'/'review-manifest.json').read_text())
    payload = dict(stage=str(job/'asset'/'review.usda'), workflow_id=workflow_id,
                   asset_id=job.name, source_sha256=manifest['source_sha256'])
    request = Request('http://127.0.0.1:8081/asset', data=json.dumps(payload).encode(), method='POST',
                      headers={'Content-Type':'application/json', 'X-Viewer-Token':os.environ['CAD_UI_VIEWER_TOKEN']})
    with urlopen(request, timeout=5) as response:
        response.read(4096)
    return dict(status='loading', **payload, asset_role='healed_unverified', cfd_ready=False)
