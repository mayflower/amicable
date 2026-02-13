from src.templates.registry import parse_template_id, template_spec


def test_parse_template_id_supports_flutter() -> None:
    assert parse_template_id("flutter") == "flutter"


def test_template_spec_for_flutter() -> None:
    spec = template_spec("flutter")
    assert spec.template_id == "flutter"
    assert spec.k8s_sandbox_template_name == "amicable-sandbox-flutter"
    assert spec.db_inject_kind == "none"
