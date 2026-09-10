import pytest
from cad_defeature.api.viewer_assets import output_for


def state(path=None):
    return dict(workflow_id='abcdef123456', healing={'status':'complete'},
                active_model=path or '/sandbox/ui/runs/abcdef123456/heal-1/healed.brep')


def test_own_output():
    assert output_for(state()).endswith('healed.brep')


@pytest.mark.parametrize('path', ['/etc/passwd', '/sandbox/ui/runs/111111111111/healed.brep',
                                 '/sandbox/ui/runs/abcdef123456/../other/healed.brep'])
def test_reject_foreign_output(path):
    with pytest.raises(ValueError):output_for(state(path))


def test_failed_healing_not_source_fallback():
    value=state();value['healing']['status']='error'
    with pytest.raises(ValueError, match='no successful'):output_for(value)
