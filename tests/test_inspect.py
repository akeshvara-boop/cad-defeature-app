from cad_defeature.inspect import inspect_model


def test_inspect_missing_file() -> None:
    result = inspect_model("does-not-exist.step")

    assert result["exists"] is False
    assert result["status"] == "input_not_found"
    assert result["supported_format"] is True


def test_inspect_existing_step_file(tmp_path) -> None:
    model = tmp_path / "part.step"
    model.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")

    result = inspect_model(model)

    assert result["exists"] is True
    assert result["supported_format"] is True
    assert result["size_bytes"] > 0
    # The intentionally minimal STEP text is not valid exchange data. Once an
    # OpenCascade kernel is available, inspection should report a structured
    # import diagnostic rather than treating the fixture as a valid model.
    assert result["status"] == "kernel_import_failed"
    assert "diagnostic" in result
