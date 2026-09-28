# Testing and release checks

TTSForge declares a dependency on Readio `>=0.3.3`. The public API contract test checks
that the installed Readio exposes the synthesis request, expanded resolution fields,
catalog types, and services required by the frontend. For development against a sibling
Readio checkout, install both projects editable:

```bash
python -m pip install -e ../readio -e ".[dev]"
```

Run the suite and lint:

```bash
pytest -q
ruff check ttsforge tests
```

The tests cover the public `readio.api` contract, request mapping, guided catalog
selection and capability gates, project reuse and legacy-workspace handling, chapter
selection, preflight and interaction modes, scoped progress, CLI behavior, package
metadata, and CI configuration. Use `tests/test_readio_api_contract.py` to diagnose an
incompatible Readio installation.

## Publishing checks

Before a TTSForge package release:

1. Test against the declared Readio floor, `0.3.3`, and the newest supported Readio
   release.
2. Install TTSForge into a clean environment, run `pip check`, and smoke-test
   `ttsforge --help` and `ttsforge doctor`.
3. Exercise an audiobook workflow with a supported engine, including project reuse and
   output export.

The local Readio checkout is useful for development but does not replace
clean-environment installation and packaging checks.
