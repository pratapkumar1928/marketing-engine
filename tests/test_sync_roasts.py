import importlib.util
from pathlib import Path

FIX = Path(__file__).parent / "fixtures" / "strings.xml"
spec = importlib.util.spec_from_file_location("sync_roasts", Path(__file__).parent.parent / "tools" / "sync_roasts.py")
sync_roasts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_roasts)


def test_parse_pairs_8_personas_40_lines():
    items = sync_roasts.parse(FIX.read_text(encoding="utf-8"))
    assert len(items) == 40
    assert len({i["persona"] for i in items}) == 8
    assert len({i["id"] for i in items}) == 40


def test_parse_keeps_text_verbatim_and_unescapes_android():
    items = {i["id"]: i for i in sync_roasts.parse(FIX.read_text(encoding="utf-8"))}
    g = items["grandma-0"]
    assert g["persona"] == "The Grandma" and g["headline"] == "In my day" and g["subtitle"]
    assert items["grandma-3"]["headline"] == "You'll ruin your eyes"
    assert all("\\'" not in i["headline"] + i["subtitle"] for i in items.values())


def test_committed_roasts_match_source():
    import yaml
    committed = yaml.safe_load((Path(__file__).parent.parent / "apps/scrollsmack/copy/roasts.yaml").read_text(encoding="utf-8"))
    assert committed == sync_roasts.parse(FIX.read_text(encoding="utf-8"))
