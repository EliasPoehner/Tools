from core.settings import Settings


def test_roundtrip(tmp_path):
    path = tmp_path / "sub" / "settings.json"
    s = Settings(path)
    s.section("Autoklicker")["interval"] = "250"
    s.save()
    assert Settings(path).section("Autoklicker") == {"interval": "250"}


def test_missing_or_broken_file_gives_defaults(tmp_path):
    assert Settings(tmp_path / "fehlt.json").data == {}
    broken = tmp_path / "kaputt.json"
    broken.write_text("{nicht json", encoding="utf-8")
    assert Settings(broken).data == {}
    broken.write_text("[1, 2]", encoding="utf-8")
    assert Settings(broken).data == {}


def test_section_replaces_non_dict(tmp_path):
    path = tmp_path / "s.json"
    path.write_text('{"x": 5}', encoding="utf-8")
    assert Settings(path).section("x") == {}
