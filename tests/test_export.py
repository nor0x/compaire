from __future__ import annotations

import pytest

from compaire.export import _ts_type, json_schema, typescript


def test_schema_exposes_both_roots() -> None:
    schema = json_schema()
    assert schema["$ref"] == "#/$defs/Experiment"
    assert {"Experiment", "Index", "Run", "TextOutput"} <= set(schema["$defs"])


def test_arrays_of_unions_are_parenthesized() -> None:
    assert "outputs?: (TextOutput | ImageOutput | HtmlOutput | SvgOutput)[];" in typescript()


def test_discriminators_are_required_so_typescript_can_narrow() -> None:
    ts = typescript()
    assert '  kind: "text";' in ts
    assert '  kind?: "text";' not in ts


def test_optional_fields_become_nullable() -> None:
    assert "description?: string | null;" in typescript()


def test_extra_allow_models_get_an_index_signature() -> None:
    ts = typescript()
    params = ts.split("export interface PromptParams {")[1].split("}")[0]
    assert "[key: string]: unknown;" in params


def test_unsupported_nodes_fail_loudly() -> None:
    with pytest.raises(ValueError, match="cannot express"):
        _ts_type({"type": "tuple"})
