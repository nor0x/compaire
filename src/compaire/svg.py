"""Make model-produced SVG safe to commit and to render.

SVG is the one asset kind that is dangerous on its own. The website renders it
through an ``<img>`` tag, which executes no scripts and loads nothing external —
but the file also sits in the repository under a URL, and a browser pointed
straight at it treats it as a live same-origin document. So the bytes themselves
have to be clean, not just the way we display them.

``sanitize`` runs at write time and reports what it removed, so the site can
tell the reader the stored artifact is not byte-for-byte what the model
returned. ``findings`` runs again in ``compaire validate``, which is what catches
a hand-edited asset in a pull request.

Input is bounded before it reaches here — model output by ``max_tokens``,
committed assets by the per-asset size limit — so entity-expansion tricks have
nothing to work with.
"""

from __future__ import annotations

import re
from xml.etree import ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

# Serialize back to plain `<svg>` and `xlink:href` instead of `ns0:` prefixes.
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)

#: Elements that exist to run code or to embed a whole other document.
FORBIDDEN_TAGS = frozenset({"script", "foreignObject", "handler", "listener"})

#: SMIL can rewrite an attribute after load; animating `href` or an event
#: handler is a well-known way to smuggle script past a naive tag filter.
ANIMATION_TAGS = frozenset({"animate", "animateTransform", "set", "animateMotion"})

HREF_ATTRS = ("href", f"{{{XLINK_NS}}}href")

#: The only references that stay: same-document fragments and inline data URIs.
SAFE_HREF_RE = re.compile(r"^\s*(?:#[^\s]*|data:image/(?:png|jpeg|gif|webp);base64,[\w+/=\s]+)$")

IMPORT_RE = re.compile(r"@import\b[^;}]*;?", re.IGNORECASE)
LENGTH_RE = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*(px|pt)?\s*$", re.IGNORECASE)


class SvgError(ValueError):
    """The input is not usable as an SVG at all."""


def parse(data: bytes | str) -> ET.Element:
    """Parse and confirm the document really is an SVG."""
    try:
        root = ET.fromstring(data if isinstance(data, str) else data.decode("utf-8"))
    except (ET.ParseError, UnicodeDecodeError) as exc:
        raise SvgError(f"not well-formed XML: {exc}") from exc
    if localname(root.tag) != "svg":
        raise SvgError(f"root element is <{localname(root.tag)}>, expected <svg>")
    return root


def localname(tag: object) -> str:
    """Tag name without its namespace. Models often omit the xmlns entirely."""
    if not isinstance(tag, str):  # comments and processing instructions
        return ""
    return tag.rsplit("}", 1)[-1]


def sanitize(data: bytes) -> tuple[bytes, list[str]]:
    """Return cleaned bytes and a human-readable list of what was removed.

    Idempotent: sanitizing the result again removes nothing, which is what lets
    ``compaire validate`` re-check a committed file with the same rules.
    """
    root = parse(data)
    removed = _clean(root, mutate=True)

    # A standalone .svg without the namespace does not render in an <img>, and
    # models leave it off often enough to be worth repairing here.
    if localname(root.tag) == root.tag and not root.get("xmlns"):
        root.set("xmlns", SVG_NS)

    cleaned = ET.tostring(root, encoding="utf-8", xml_declaration=False)
    return cleaned, removed


def findings(data: bytes) -> list[str]:
    """What sanitize *would* remove. Empty means the file is already clean."""
    return _clean(parse(data), mutate=False)


def intrinsic_size(data: bytes) -> tuple[int | None, int | None]:
    """Pixel size from `width`/`height`, falling back to the viewBox."""
    try:
        root = parse(data)
    except SvgError:
        return None, None

    width, height = _length(root.get("width")), _length(root.get("height"))
    if width and height:
        return width, height

    box = (root.get("viewBox") or "").replace(",", " ").split()
    if len(box) == 4:
        return width or _length(box[2]), height or _length(box[3])
    return width, height


def _clean(root: ET.Element, *, mutate: bool) -> list[str]:
    removed: list[str] = []

    # Materialized up front: removing children while walking a live iterator
    # silently skips siblings.
    for parent in list(root.iter()):
        for child in list(parent):
            name = localname(child.tag)
            if name in FORBIDDEN_TAGS:
                removed.append(f"<{name}>")
                if mutate:
                    parent.remove(child)
                continue
            if name in ANIMATION_TAGS and _animates_dangerously(child):
                removed.append(f"<{name} attributeName={child.get('attributeName')!r}>")
                if mutate:
                    parent.remove(child)

    for element in list(root.iter()):
        if not isinstance(element.tag, str):
            continue
        for attribute, value in list(element.attrib.items()):
            reason = _attribute_problem(localname(element.tag), attribute, value)
            if reason:
                removed.append(reason)
                if mutate:
                    del element.attrib[attribute]

        if localname(element.tag) == "style" and element.text and IMPORT_RE.search(element.text):
            removed.append("@import in <style>")
            if mutate:
                element.text = IMPORT_RE.sub("", element.text)

    return removed


def _attribute_problem(tag: str, attribute: str, value: str) -> str | None:
    bare = localname(attribute)
    if bare.lower().startswith("on"):
        return bare
    if attribute in HREF_ATTRS and not SAFE_HREF_RE.match(value):
        return f"{bare} to {_shorten(value)} on <{tag}>"
    return None


def _animates_dangerously(element: ET.Element) -> bool:
    # attributeName is a QName like "xlink:href", not Clark notation.
    target = (element.get("attributeName") or "").lower()
    return target.startswith("on") or target.split(":")[-1] == "href"


def _length(value: str | None) -> int | None:
    if not value:
        return None
    match = LENGTH_RE.match(value)
    return round(float(match.group(1))) if match else None


def _shorten(value: str, limit: int = 40) -> str:
    flat = " ".join(value.split())
    return flat if len(flat) <= limit else f"{flat[:limit]}…"
