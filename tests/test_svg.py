"""The SVG sanitizer — the one asset check that is about safety, not rendering."""

from __future__ import annotations

import pytest

from compaire import svg


def doc(body: str = "", attrs: str = 'xmlns="http://www.w3.org/2000/svg"') -> bytes:
    return f"<svg {attrs} viewBox='0 0 10 10'>{body}</svg>".encode()


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ('<script>alert(1)</script>', "<script>"),
        ('<foreignObject><b>hi</b></foreignObject>', "<foreignObject>"),
        ('<rect onclick="steal()"/>', "onclick"),
        ('<rect onLoad="steal()"/>', "onLoad"),
        ('<a href="https://evil.example">x</a>', "href to https://evil.example on <a>"),
        ('<image href="//evil.example/p.png"/>', "href to //evil.example/p.png on <image>"),
        ('<a xlink:href="javascript:alert(1)" xmlns:xlink="http://www.w3.org/1999/xlink"/>',
         "href to javascript:alert(1) on <a>"),
        ('<style>@import url(https://evil.example/x.css);</style>', "@import in <style>"),
        ('<animate attributeName="onload" to="alert(1)"/>', "<animate"),
        ('<set attributeName="xlink:href" to="javascript:alert(1)"/>', "<set"),
    ],
)
def test_dangerous_constructs_are_removed(body: str, expected: str) -> None:
    cleaned, removed = svg.sanitize(doc(body))
    assert any(expected in item for item in removed), removed
    assert svg.findings(cleaned) == []


@pytest.mark.parametrize(
    "body",
    [
        '<use href="#glyph"/>',
        '<image href="data:image/png;base64,iVBORw0KGgo="/>',
        '<rect fill="red" stroke-width="2"/>',
        '<style>.a { fill: blue }</style>',
        '<animate attributeName="opacity" to="0.5"/>',
        '<text font-family="sans-serif">hello</text>',
    ],
)
def test_ordinary_drawing_content_survives(body: str) -> None:
    cleaned, removed = svg.sanitize(doc(body))
    assert removed == []
    assert svg.findings(cleaned) == []


def test_sanitize_is_idempotent() -> None:
    dirty = doc('<script>x</script><rect onclick="y()"/><a href="https://e.example"/>')
    once, first = svg.sanitize(dirty)
    twice, second = svg.sanitize(once)
    assert first and second == []
    assert once == twice


def test_findings_does_not_modify_its_input() -> None:
    dirty = doc('<script>x</script>')
    assert svg.findings(dirty)
    assert svg.findings(dirty)  # a mutating implementation would come back empty


@pytest.mark.parametrize(
    "data",
    [b"<svg>unclosed", b"not xml at all", b"<html><body>nope</body></html>", b""],
)
def test_unusable_input_is_rejected(data: bytes) -> None:
    with pytest.raises(svg.SvgError):
        svg.sanitize(data)


def test_missing_namespace_is_repaired() -> None:
    """A standalone .svg without the namespace does not render in an <img>."""
    cleaned, _ = svg.sanitize(b"<svg viewBox='0 0 4 4'><rect/></svg>")
    assert b'xmlns="http://www.w3.org/2000/svg"' in cleaned


def test_namespaced_input_round_trips_without_prefixes() -> None:
    cleaned, _ = svg.sanitize(doc("<rect/>"))
    assert b"ns0:" not in cleaned
    assert cleaned.startswith(b"<svg")


@pytest.mark.parametrize(
    ("attrs", "expected"),
    [
        ('width="512" height="256"', (512, 256)),
        ('width="512px" height="256px"', (512, 256)),
        ('width="100%" height="100%"', (10, 10)),  # falls back to the viewBox
        ("", (10, 10)),
    ],
)
def test_intrinsic_size(attrs: str, expected: tuple[int, int]) -> None:
    data = f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 10' {attrs}/>".encode()
    assert svg.intrinsic_size(data) == expected


def test_intrinsic_size_of_garbage_is_unknown() -> None:
    assert svg.intrinsic_size(b"nope") == (None, None)


def test_nested_hazards_are_reached() -> None:
    cleaned, removed = svg.sanitize(doc('<g><g><rect onclick="x()"/><script>y</script></g></g>'))
    assert sorted(removed) == ["<script>", "onclick"]
    assert svg.findings(cleaned) == []


def test_sibling_after_a_removed_element_is_still_checked() -> None:
    """Removing while walking a live iterator would skip the second script."""
    _, removed = svg.sanitize(doc("<script>a</script><script>b</script>"))
    assert removed == ["<script>", "<script>"]
