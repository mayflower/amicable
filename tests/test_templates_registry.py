from src.templates.registry import parse_template_id, template_spec


def test_parse_template_id_supports_flutter() -> None:
    assert parse_template_id("flutter") == "flutter"


def test_parse_template_id_supports_phoenix() -> None:
    assert parse_template_id("phoenix") == "phoenix"


def test_parse_template_id_supports_aspnetcore() -> None:
    assert parse_template_id("aspnetcore") == "aspnetcore"


def test_parse_template_id_supports_quarkus() -> None:
    assert parse_template_id("quarkus") == "quarkus"


def test_template_spec_for_flutter() -> None:
    spec = template_spec("flutter")
    assert spec.template_id == "flutter"
    assert spec.k8s_sandbox_template_name == "amicable-sandbox-flutter"
    assert spec.db_inject_kind == "none"


def test_template_spec_for_phoenix() -> None:
    spec = template_spec("phoenix")
    assert spec.template_id == "phoenix"
    assert spec.k8s_sandbox_template_name == "amicable-sandbox-phoenix"
    assert spec.db_inject_kind == "none"


def test_template_spec_for_aspnetcore() -> None:
    spec = template_spec("aspnetcore")
    assert spec.template_id == "aspnetcore"
    assert spec.k8s_sandbox_template_name == "amicable-sandbox-aspnetcore"
    assert spec.db_inject_kind == "none"


def test_template_spec_for_quarkus() -> None:
    spec = template_spec("quarkus")
    assert spec.template_id == "quarkus"
    assert spec.k8s_sandbox_template_name == "amicable-sandbox-quarkus"
    assert spec.db_inject_kind == "none"
