# Testing and release checks

Development and tests use the local Readio checkout because the compatible public API is
not yet available from PyPI. From the TTSForge repository, install the sibling checkout
and development dependencies:

```bash
python -m pip install -e ../readio -e ".[dev]"
```

Run the suite and lint:

```bash
pytest -q
ruff check ttsforge tests
```

The tests cover the public `readio.api` contract, request mapping, project reuse and
legacy-workspace handling, chapter selection, event progress, CLI behavior, package
metadata, and CI configuration. The API contract test asserts the required public API
version and symbols; use `tests/test_readio_api_contract.py` to diagnose an incompatible
local Readio checkout.

## Publishing compatibility gate

A compatible published Readio release must exist before setting a Readio minimum version
or declaring a clean installation successful. Before a TTSForge package release:

1. Set the dependency floor to the first published Readio release with the complete
   required API.
2. Test against that floor and the newest compatible Readio release.
3. Install TTSForge into a clean environment from PyPI, run `pip check`, and smoke-test
   `ttsforge --help`, `ttsforge doctor`, and an audiobook workflow.

Until those prerequisites exist, the published-version pin and PyPI clean-install gate
are blocked. Do not substitute a local checkout for the clean PyPI test or guess a
version number.
