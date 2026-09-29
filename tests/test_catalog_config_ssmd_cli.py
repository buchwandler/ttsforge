"""CLI delegation tests for Readio catalog, config, diagnostics, and SSMD APIs."""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

from readio.api import (
    CatalogDiscovery,
    CatalogListing,
    DiscoveryOptions,
    EngineInfo,
    ModelInfo,
    ModelQuery,
    SSMDMaterializeResult,
    VoiceInfo,
    VoiceQuery,
)
from typer.testing import CliRunner

cli_module = import_module("ttsforge.cli.app")
runner = CliRunner()


def test_voices_and_models_delegate_queries_to_catalog(monkeypatch) -> None:
    voice = VoiceInfo(
        selector="en-us:af_heart",
        id="af_heart",
        gender="female",
        language="en",
        locale="en-US",
        language_label="English",
        model="kokoro-v1",
        source="kokoro",
        default=False,
        status="ready",
        experimental=False,
        runtime_available=True,
    )
    model = ModelInfo(
        id="kokoro-v1",
        source="kokoro",
        languages=("en-US",),
        voices=("af_heart",),
        default_voice="af_heart",
        qualities=("fp32",),
        g2p_backend=None,
        lexicons=(),
        frontend="kokoro",
        status="ready",
        experimental=False,
        runtime_available=True,
        redistribution_allowed=True,
    )
    engine = EngineInfo(
        id="piper",
        version="2.0",
        registered=True,
        installed=False,
        runnable=False,
        capabilities=None,
        missing_dependency="piper runtime",
    )
    discovery = CatalogDiscovery(registry_source="test")
    calls: list[tuple[str, object, DiscoveryOptions]] = []

    def voices_listing(query, *, discovery):  # type: ignore[no-untyped-def]
        calls.append(("voices", query, discovery))
        return CatalogListing((voice,), discovery=CatalogDiscovery("test"))

    def models_listing(query, *, discovery):  # type: ignore[no-untyped-def]
        calls.append(("models", query, discovery))
        return CatalogListing((model,), discovery=CatalogDiscovery("test"))

    api = SimpleNamespace(
        catalog=SimpleNamespace(
            voices_listing=voices_listing,
            models_listing=models_listing,
            engines=lambda: (engine,),
        )
    )
    monkeypatch.setattr(cli_module, "_readio", lambda: api)

    voices = runner.invoke(
        cli_module.app,
        ["voices", "--engine", "kokoro", "--language", "en-US", "--offline", "--json"],
    )
    models = runner.invoke(
        cli_module.app,
        ["models", "--engine", "piper", "--status", "ready", "--refresh", "--json"],
    )

    engines_json = runner.invoke(cli_module.app, ["engines", "--json"])
    human_voices = runner.invoke(cli_module.app, ["voices"])
    human_models = runner.invoke(cli_module.app, ["models"])
    human_engines = runner.invoke(cli_module.app, ["engines"])
    assert voices.exit_code == 0, voices.output
    assert models.exit_code == 0, models.output
    assert json.loads(voices.stdout)["items"][0]["id"] == "af_heart"
    assert json.loads(models.stdout)["items"][0]["id"] == "kokoro-v1"
    assert json.loads(voices.stdout)["items"][0]["selector"] == "en-us:af_heart"
    assert engines_json.exit_code == 0, engines_json.output
    assert json.loads(engines_json.stdout)[0]["runnable"] is False
    assert all(
        result.exit_code == 0 for result in (human_voices, human_models, human_engines)
    )
    assert "Voices (1)" in human_voices.output
    assert human_voices.output.index("af_heart") < human_voices.output.index(
        "selector: en-us:af_heart"
    )
    assert "Models (1)" in human_models.output
    assert "kokoro-v1" in human_models.output
    assert "Engines (1)" in human_engines.output
    assert "not runnable" in human_engines.output
    assert "missing dependency: piper runtime" in human_engines.output
    assert not any(
        border in result.output
        for result in (human_voices, human_models, human_engines)
        for border in ("┏", "┓", "┃", "┡", "└")
    )
    assert calls[0] == (
        "voices",
        VoiceQuery(language="en-US", engine="kokoro"),
        DiscoveryOptions(offline=True),
    )
    assert calls[1] == (
        "models",
        ModelQuery(engine="piper", status="ready"),
        DiscoveryOptions(refresh=True),
    )
    assert discovery.registry_source == "test"


def test_config_set_uses_readio_configuration_service(
    monkeypatch, tmp_path: Path
) -> None:
    path = tmp_path / "readio.toml"
    changes: list[tuple[str, object, Path | None]] = []

    def set_value(key: str, value: object, *, path: Path | None = None) -> object:
        changes.append((key, value, path))
        return object()

    api = SimpleNamespace(
        configuration=SimpleNamespace(
            path=lambda: path,
            set_value=set_value,
        )
    )
    monkeypatch.setattr(cli_module, "_readio", lambda: api)

    result = runner.invoke(
        cli_module.app,
        ["config", "set", "reader.speed", "1.25", "--path", str(path)],
    )

    assert result.exit_code == 0, result.output
    assert changes == [("reader.speed", 1.25, path)]
    assert "Updated Readio setting" in result.stdout


def test_doctor_formats_and_ssmd_commands_use_public_services() -> None:
    doctor = runner.invoke(cli_module.app, ["doctor", "--json"])
    formats = runner.invoke(cli_module.app, ["formats", "--json"])
    source = Path(__file__).parent / "fixtures" / "readio_ssmd09_minimal.ssmd"
    analysis = runner.invoke(cli_module.app, ["ssmd", "analyze", str(source), "--json"])
    check = runner.invoke(cli_module.app, ["ssmd", "check", str(source), "--json"])
    validate = runner.invoke(
        cli_module.app, ["ssmd", "validate", str(source), "--json"]
    )

    assert doctor.exit_code == 0, doctor.output
    assert json.loads(doctor.stdout)["readio_version"]
    assert formats.exit_code == 0, formats.output
    assert {item["id"] for item in json.loads(formats.stdout)} >= {"wav", "m4b"}
    assert analysis.exit_code == 0, analysis.output
    assert check.exit_code == 0, check.output
    assert validate.exit_code == 0, validate.output
    analysis_payload = json.loads(analysis.stdout)
    assert analysis_payload["source_path"].endswith("readio_ssmd09_minimal.ssmd")


def test_ssmd_materialize_passes_bindings_to_readio(
    monkeypatch, tmp_path: Path
) -> None:
    source = Path(__file__).parent / "fixtures" / "readio_ssmd09_minimal.ssmd"
    output = tmp_path / "bound.ssmd"
    expected = SSMDMaterializeResult(
        source_path=source,
        output_path=output,
        provider="kokoro",
        binding_count=1,
        in_place=False,
    )
    calls: list[tuple[Path, dict[str, str], dict[str, object]]] = []

    def materialize(source_path, bindings, **kwargs):  # type: ignore[no-untyped-def]
        calls.append((source_path, bindings, kwargs))
        return expected

    api = SimpleNamespace(ssmd=SimpleNamespace(materialize_bindings=materialize))
    monkeypatch.setattr(cli_module, "_readio", lambda: api)

    result = runner.invoke(
        cli_module.app,
        [
            "ssmd",
            "materialize",
            str(source),
            "--bindings",
            '{"narrator":"af_sarah"}',
            "--provider",
            "kokoro",
            "--output",
            str(output),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls == [
        (
            source,
            {"narrator": "af_sarah"},
            {"provider": "kokoro", "output": output, "in_place": False},
        )
    ]
    assert json.loads(result.stdout)["binding_count"] == 1
