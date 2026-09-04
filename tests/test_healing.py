from cad_defeature.healing import DEFAULT_TOLERANCES


def test_healing_tolerances_are_conservative_and_ordered() -> None:
    assert DEFAULT_TOLERANCES == tuple(sorted(DEFAULT_TOLERANCES))
    assert DEFAULT_TOLERANCES[0] > 0
