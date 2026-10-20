from core.registry import Tool, discover_tools


def test_discovers_autoclicker():
    tools = discover_tools()
    names = [t.name for t in tools]
    assert "Autoklicker" in names
    assert all(issubclass(t, Tool) for t in tools)


def test_tools_are_sorted_and_unique():
    tools = discover_tools()
    names = [t.name for t in tools]
    assert names == sorted(names, key=str.lower)
    assert len(set(tools)) == len(tools)
