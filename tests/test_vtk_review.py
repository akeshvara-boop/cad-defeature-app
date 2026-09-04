import json

from cad_defeature.trame_review import load_manifest


def test_load_manifest_accepts_highlight_schema(tmp_path) -> None:
    manifest_path = tmp_path / "highlights.json"
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_type": "cad_defeature_face_highlights",
                "summary": {"highlight_count": 0, "by_status": {}},
                "highlights": [],
            }
        ),
        encoding="utf-8",
    )

    assert load_manifest(manifest_path)["highlights"] == []


def test_load_manifest_rejects_unexpected_schema(tmp_path) -> None:
    manifest_path = tmp_path / "other.json"
    manifest_path.write_text(json.dumps({"manifest_type": "other"}), encoding="utf-8")

    try:
        load_manifest(manifest_path)
    except ValueError as error:
        assert "cad_defeature_face_highlights" in str(error)
    else:
        raise AssertionError("Expected invalid manifest to be rejected")
