# Testing and integration checks

TTSForge requires Readio `>=0.6.1,<0.7`. The public API contract test checks the
gateway, typed render/workflow contracts, source inspection, intent/profile helpers,
discovery operations, and normalized progress types required by the adapter.

For local development, use a Readio checkout that satisfies the declared dependency
floor and install both projects editable:

```bash
python -m pip install -e ../readio -e ".[dev]"
```

Run tests, lint, and type checking from the TTSForge checkout:

```bash
python -m pytest -q
ruff check .
mypy ttsforge
```

The test suite covers the public `readio.api` boundary, saved setup and retry behavior,
setup precedence and dependent-choice invalidation, chapter selection, workflow
delegation, progress and error presentation, CLI commands, packaging, and legacy-project
safety. `tests/test_readio_api_contract.py` identifies missing or incompatible Readio
APIs.

## Practical acceptance checks

Before a package release, exercise a real conversion with Readio `>=0.6.1,<0.7` and a
supported engine integration:

1. Convert a fresh EPUB to the default M4B and verify the `.ttsforge/` intent, profile,
   and bundle paths.
2. Re-run the conversion and verify that Readio reports reusable work.
3. Cause a render/runtime failure after setup, then retry and verify that the saved
   setup is reused.
4. Verify that an existing output is not replaced without `--replace-output`.
5. Verify that `--rebuild-from` reaches Readio independently of output replacement.
6. Verify that a legacy TTSForge/Readio 0.4 project is rejected without mutation.

Tests that require a Readio 0.6.1 installation or a real engine runtime cannot be
established by a lower-version development checkout alone.
