# TTSForge 0.3.4 Release Implementation Brief

## Purpose

Prepare **TTSForge 0.3.4** so that its supported minimum generation stack is:

- `pykokoro[cpu]>=0.8.3,<0.9`
- `kokorog2p[espeak,en]>=0.8.0,<0.9`

The release must also align the effective SSMD floor with PyKokoro 0.8.3:

- `ssmd>=0.8.1,<0.9`

This is not only a dependency-metadata bump. PyKokoro 0.8.3 and kokorog2p 0.8.0
introduce a meaningful written-to-spoken preparation boundary, so the release must also
update the resumable-generation contract, regression tests, CI minimum-version coverage,
and user documentation.

---

## 1. Audit basis

### Dependency snapshots reconstructed locally

The supplied Codecrate snapshots were reconstructed with strict manifest and hash
validation:

```bash
python3 -S context_pykokoro.unpack.py context_pykokoro.md \
  -o reconstructed/pykokoro \
  --check-machine-header --strict --fail-on-warning

python3 -S context_kokorog2p.unpack.py context_kokorog2p.md \
  -o reconstructed/kokorog2p \
  --check-machine-header --strict --fail-on-warning
```

Both reconstructions completed without unpack warnings.

The inspected PyKokoro snapshot is prepared as **0.8.3** and declares:

```toml
"kokorog2p[espeak,en]>=0.8.0,<0.9"
"ssmd>=0.8.1,<0.9"
"phrasplit>=0.3.4,<0.4"
"audiosig>=0.1.1,<0.2"
```

Its `setuptools_scm` fallback is `0.8.3`.

The inspected kokorog2p snapshot is prepared as **0.8.0** and declares the new shared
written-to-spoken dependencies:

```toml
"abbr2words>=0.2.9,<0.3.0"
"spokenform>=0.2.6,<0.3.0"
```

### TTSForge source inspected

The current TTSForge `main` branch was inspected at:

```text
31eb8dd7b6bc49f05a95cf5de197d0b8ef74d49c
```

The repository already contains a planned **0.3.4** release object. Do not create a
competing 0.3.4 or skip directly to another version unless releaseledger state has
changed before implementation.

A local TTSForge Codecrate pack was not mounted in this turn, and the sandbox could not
resolve GitHub for `git clone`; current TTSForge files were therefore inspected through
the connected GitHub repository rather than reconstructed locally.

### Public package-index status checked on 2026-08-15

At audit time, the public PyPI release histories still expose:

- PyKokoro latest: **0.8.1**
- kokorog2p latest: **0.7.2**

Therefore **TTSForge 0.3.4 must not be published to public PyPI with the new floors
until kokorog2p 0.8.0 and PyKokoro 0.8.3 have been published and can be installed from
the same target package index**.

The coordinated publication order should be:

1. kokorog2p 0.8.0
2. PyKokoro 0.8.3
3. TTSForge 0.3.4

---

# 2. Executive findings

## Release blockers

### B1 — TTSForge still requires PyKokoro 0.8.2

Current TTSForge metadata contains:

```toml
"pykokoro[cpu]>=0.8.2,<0.9"
```

Change it to:

```toml
"pykokoro[cpu]>=0.8.3,<0.9"
```

### B2 — TTSForge directly imports kokorog2p but does not declare it directly

Production code directly consumes kokorog2p in at least:

- `ttsforge/name_extractor.py`
- `ttsforge/vocab/__init__.py`

`ttsforge/vocab/__init__.py` directly imports `kokorog2p` plus public vocabulary
constants and helpers.

`ttsforge/name_extractor.py` directly imports `kokorog2p.phonemize()` for phoneme
suggestions.

Do not rely only on PyKokoro's transitive dependency for a package that TTSForge imports
directly.

Add:

```toml
"kokorog2p[espeak,en]>=0.8.0,<0.9"
```

This deliberately mirrors the supported PyKokoro 0.8.3 runtime boundary.

### B3 — SSMD metadata is internally inconsistent with the new PyKokoro floor

TTSForge currently declares:

```toml
"ssmd>=0.8.0,<0.9"
```

PyKokoro 0.8.3 requires:

```toml
"ssmd>=0.8.1,<0.9"
```

Because PyKokoro is a mandatory TTSForge dependency, `ssmd==0.8.0` can no longer be the
effective install minimum. Keeping the weaker TTSForge constraint is misleading.

Change TTSForge to:

```toml
"ssmd>=0.8.1,<0.9"
```

### B4 — resumable generation still identifies the PyKokoro renderer as 0.8.1

`ttsforge/render_units.py` currently contains:

```python
PYKOKORO_RENDERER_VERSION = "0.8.1"
```

and:

```python
def renderer_contract_payload() -> dict[str, object]:
    return {
        "schema": 2,
        "ssmd": "0.8",
        "pykokoro": PYKOKORO_RENDERER_VERSION,
        ...
    }
```

This is stale and is release-critical.

kokorog2p 0.8.0 changes the text that can reach G2P for ordinary written forms. A
conversion that starts under the old stack must not silently resume under the new
written-to-spoken semantics and combine audio generated under two semantic contracts.

Update the semantic renderer contract.

Recommended shape:

```python
PYKOKORO_RENDERER_VERSION = "0.8.3"
KOKOROG2P_TEXT_PREPARATION_VERSION = "0.8.0"

def renderer_contract_payload() -> dict[str, object]:
    return {
        "schema": 3,
        "ssmd": "0.8",
        "pykokoro": PYKOKORO_RENDERER_VERSION,
        "kokorog2p": KOKOROG2P_TEXT_PREPARATION_VERSION,
        "paragraph_unit": 1,
        "pause_ownership": PARAGRAPH_PAUSE_OWNERSHIP,
        "unit_filename_schema": UNIT_FILENAME_SCHEMA,
        "paragraph_manifest_schema": PARAGRAPH_MANIFEST_SCHEMA,
    }
```

Important: these values should represent the **semantic generation contract**, not
blindly mirror the exact runtime patch version forever.

If a future PyKokoro 0.8.4 is fully generation-compatible, no resume invalidation is
needed merely because the package version changed. If a future dependency changes
generated semantics, explicitly bump the renderer contract again.

### B5 — do not bump `GENERATION_IDENTITY_SCHEMA` for this change

`ttsforge/resume_identity.py` currently uses:

```python
GENERATION_IDENTITY_SCHEMA = 2
```

Keep it at **2** for this release.

The current resume validator treats a saved identity whose schema differs from the
current schema as corrupt. Blindly changing `GENERATION_IDENTITY_SCHEMA` from 2 to 3
would convert a normal compatibility mismatch into:

```text
generation-identity-corrupt
```

That is the wrong user-facing behavior.

The renderer contract is already embedded inside the generation-identity payload through
the SSMD policy payload. Changing:

- renderer contract schema `2 -> 3`
- PyKokoro contract `0.8.1 -> 0.8.3`
- adding kokorog2p contract `0.8.0`

is sufficient to change the generation fingerprint while preserving the existing
schema-2 validation path and field-level difference reporting.

Expected mismatch paths should include some or all of:

```text
ssmd_policy.renderer_contract.schema
ssmd_policy.renderer_contract.pykokoro
ssmd_policy.renderer_contract.kokorog2p
```

This is a substantially better migration than marking an otherwise well-formed state
file as corrupt.

### B6 — dependency versions are not yet on public PyPI

The supplied releaseledgers mark both dependency releases as `planned`, and the public
package index still reports older public releases.

TTSForge 0.3.4 must have a hard release gate:

```bash
python -m pip install --no-cache-dir \
  "kokorog2p[espeak,en]==0.8.0" \
  "pykokoro[cpu]==0.8.3"
```

This must succeed from the same index TTSForge will be published to before finalizing
0.3.4.

---

# 3. Compatibility review of PyKokoro 0.8.3

The TTSForge runner currently imports these important PyKokoro interfaces:

```text
GenerationConfig
KokoroPipeline
PipelineConfig

DEFAULT_MODEL_QUALITY
DEFAULT_MODEL_SOURCE
DEFAULT_MODEL_VARIANT
Kokoro
ModelQuality
ModelSource
ModelVariant
VoiceBlend
are_models_downloaded
download_all_models
download_all_models_github

build_pipeline
ShortSentenceConfig

OnnxAudioGenerationAdapter
OnnxAudioPostprocessingAdapter
OnnxPhonemeProcessorAdapter
```

Static inspection of the reconstructed PyKokoro 0.8.3 snapshot confirms that the
corresponding modules/symbols are still present.

The public paragraph-unit contract used by TTSForge is also still present in 0.8.3:

```text
KokoroPipeline.prepare_units()
PreparedAudioUnits.units
PreparedAudioUnits.render(skip_indices=...)
AudioUnitDescriptor.text_hash
AudioUnitResult.release_audio()
```

Therefore no broad runner rewrite is indicated by the inspected 0.8.3 source.

The required TTSForge changes are mainly:

- metadata floors;
- semantic resume contract;
- stale minimum-version messages;
- direct dependency ownership;
- tests/CI;
- documentation.

---

# 4. What changed semantically in the dependency stack

PyKokoro 0.8.3 intentionally raises kokorog2p to 0.8.0 and adds regression coverage for
source-aware written-to-spoken preparation.

The upstream regression input includes ordinary source text such as:

```text
Dr. Smith will see you at 10:30 on 05/20/2023.
The box weighs 5 kg and costs $10.99.
The temperature is 98.6°F.
She finished in 1st place.
```

The 0.8.0 stack prepares spoken forms including concepts such as:

```text
Doctor Smith
ten thirty
May twentieth
five kilograms
ten dollars
ninety eight point six degrees Fahrenheit
first place
```

This is why the update is not equivalent to a normal implementation-only patch bump.

The ownership model should be documented as:

```text
source text
    |
    v
TTSForge document/extraction/SSMD orchestration
    |
    v
PyKokoro pipeline
    |
    v
kokorog2p 0.8.x written-to-spoken preparation
    |
    v
language G2P / phoneme generation
    |
    v
Kokoro synthesis
```

TTSForge should **not** duplicate the new Spokenform normalization.

Explicit SSMD `say-as` remains an author-controlled override. Automatic normalization of
ordinary text and explicit SSMD `say-as` are related but separate responsibilities.

---

# 5. File-by-file implementation plan

## 5.1 `pyproject.toml`

### Required dependency changes

Change:

```toml
"pykokoro[cpu]>=0.8.2,<0.9",
"ssmd>=0.8.0,<0.9",
```

to:

```toml
"pykokoro[cpu]>=0.8.3,<0.9",
"kokorog2p[espeak,en]>=0.8.0,<0.9",
"ssmd>=0.8.1,<0.9",
```

Keep:

```toml
"phrasplit>=0.3.4,<0.4"
"audiosig>=0.1.2,<0.2"
```

unless another independent release requirement changes them.

### Required release fallback correction

Current:

```toml
[tool.setuptools_scm]
fallback_version = "0.3.0"
```

The repository has already released 0.3.3 and contains a planned 0.3.4 release.

For the 0.3.4 release, change to:

```toml
fallback_version = "0.3.4"
```

Add/adjust a packaging test so this cannot drift again.

### Suggested dependency block

```toml
dependencies = [
    ...
    "pykokoro[cpu]>=0.8.3,<0.9",
    "kokorog2p[espeak,en]>=0.8.0,<0.9",
    "phrasplit>=0.3.4,<0.4",
    "ssmd>=0.8.1,<0.9",
    ...
]
```

Do not add `spokenform` or `abbr2words` directly to TTSForge. kokorog2p owns those
dependencies.

---

## 5.2 `setup.py`

No dependency duplication was found.

`setup.py` delegates metadata/versioning to setuptools/setuptools-scm, so there should
be **no second dependency list** to update.

Keep it that way.

---

## 5.3 `ttsforge/render_units.py`

### Required

Replace the stale renderer semantic version.

Current:

```python
PYKOKORO_RENDERER_VERSION = "0.8.1"
```

Target:

```python
PYKOKORO_RENDERER_VERSION = "0.8.3"
KOKOROG2P_TEXT_PREPARATION_VERSION = "0.8.0"
```

Change renderer contract schema:

```python
"schema": 2,
```

to:

```python
"schema": 3,
```

Add:

```python
"kokorog2p": KOKOROG2P_TEXT_PREPARATION_VERSION,
```

### Why this belongs here

`renderer_contract_payload()` already provides the semantic generation boundary consumed
by resume identity. Keeping the dependency compatibility marker here avoids scattering
version literals through conversion code.

### Do not

Do not import heavy PyKokoro/kokorog2p modules into `render_units.py`.

The module intentionally remains dependency-light and testable without ONNX. Preserve
that property.

---

## 5.4 `ttsforge/resume_identity.py`

### Required behavior

Keep:

```python
GENERATION_IDENTITY_SCHEMA = 2
```

The renderer contract included by `_policy_payload()` should naturally produce a
different generation fingerprint after the `render_units.py` change.

No exact installed package version needs to be inserted into the generation identity for
this release.

### Optional diagnostic enhancement

If useful, installed versions may be reported separately in diagnostic output/state
metadata:

```text
pykokoro_runtime_version
kokorog2p_runtime_version
```

but those diagnostic values should not automatically affect the generation fingerprint
unless the project intentionally adopts “every patch invalidates resume” semantics.

### Required regression

Add a test showing that a schema-2 state with the old renderer contract:

```text
schema=2
pykokoro=0.8.1
(no kokorog2p key)
```

is:

- structurally valid;
- not classified as corrupt;
- rejected as `generation-fingerprint-changed`;
- accompanied by field-level renderer-contract differences.

---

## 5.5 `ttsforge/kokoro_runner.py`

Two user-facing error messages still recommend:

```text
pykokoro>=0.8.2,<0.9
```

Update both to:

```text
pykokoro>=0.8.3,<0.9
```

Prefer a single module constant to avoid future stale strings, for example:

```python
SUPPORTED_PYKOKORO = ">=0.8.3,<0.9"
```

Then:

```python
raise RuntimeError(
    "Installed PyKokoro does not provide the public paragraph-unit API; "
    f"install pykokoro{SUPPORTED_PYKOKORO}."
)
```

If using a constant, keep package metadata tests as the authoritative floor check so
code and metadata cannot silently diverge.

---

## 5.6 `ttsforge/name_extractor.py`

Production code directly imports:

```python
from kokorog2p import phonemize
```

No source rewrite is required solely for kokorog2p 0.8.0: the inspected 0.8.0 API
continues to expose phonemization results with `.phonemes`.

However, the direct dependency must be declared in `pyproject.toml`.

### Missing regression coverage

Current `tests/test_name_extractor.py` primarily tests spaCy model caching. Add coverage
for `generate_phoneme_suggestions()` so the direct kokorog2p boundary is actually
exercised.

Suggested assertions:

- one extracted name yields one suggestion;
- returned phoneme text is non-empty under kokorog2p 0.8.0;
- duplicate names do not create unstable output;
- an unsupported/failing phonemization path follows the existing intended error policy.

Do not test kokorog2p internals here.

---

## 5.7 `ttsforge/vocab/__init__.py`

The module directly imports these kokorog2p APIs:

```text
get_vocab
get_vocab_reverse
get_config
N_TOKENS
PAD_IDX
encode
decode
validate_for_kokoro
filter_for_kokoro
phonemes_to_ids
ids_to_phonemes
```

Static inspection of the supplied kokorog2p 0.8.0 snapshot confirms these names are
still present.

No compatibility rewrite is indicated.

Add a focused contract test that imports the TTSForge vocabulary compatibility layer
with kokorog2p 0.8.0 and checks at least:

```python
assert load_vocab()
assert get_vocab_info()["backend"] == "kokorog2p"
assert callable(encode)
assert callable(decode)
```

This catches future upstream API removal earlier than an audiobook conversion.

---

# 6. Pytest review and required changes

## 6.1 `tests/test_packaging.py`

This file contains several stale release assertions.

### Change TTSForge fallback assertion

Current:

```python
assert data["tool"]["setuptools_scm"]["fallback_version"] == "0.3.0"
```

Target:

```python
assert data["tool"]["setuptools_scm"]["fallback_version"] == "0.3.4"
```

### Change TTSForge PyKokoro dependency assertion

Current:

```python
assert "pykokoro[cpu]>=0.8.2,<0.9" in dependencies
```

Target:

```python
assert "pykokoro[cpu]>=0.8.3,<0.9" in dependencies
```

Also reject known older floors:

```python
assert not any("pykokoro[cpu]>=0.8.2" in dep for dep in dependencies)
assert not any("pykokoro[cpu]>=0.8.1" in dep for dep in dependencies)
```

### Add direct kokorog2p assertion

```python
assert "kokorog2p[espeak,en]>=0.8.0,<0.9" in dependencies
```

### Align SSMD assertion

Change:

```python
assert "ssmd>=0.8.0,<0.9" in dependencies
```

to:

```python
assert "ssmd>=0.8.1,<0.9" in dependencies
```

### Remove or redesign the sibling-PyKokoro metadata test

Current TTSForge test logic reaches into a sibling checkout and asserts upstream
PyKokoro's own fallback version. It currently expects `0.8.1`, and it silently skips
when the sibling checkout is absent.

This is a brittle responsibility boundary.

Preferred change:

- remove TTSForge's assertion about PyKokoro's internal
  `setuptools_scm.fallback_version`;
- let PyKokoro's own test suite own its package fallback/version metadata;
- test TTSForge's declared dependency floor and installed dependency contract instead.

If the project intentionally retains coordinated sibling-checkout testing, update the
expected PyKokoro fallback to `0.8.3`, but do not treat that optional skipped test as
proof that the released dependency works.

### Update stale import error text

The SSMD/PyKokoro importability test still mentions a much older PyKokoro minimum.

Update the failure message to the current supported floor.

---

## 6.2 `tests/test_pykokoro_unit_contract.py`

Keep the existing public paragraph-unit checks.

They are appropriate because TTSForge depends on these public PyKokoro APIs.

Add a version-independent contract assertion for any newly consumed public surface only
if TTSForge truly uses it.

Do **not** duplicate the entire PyKokoro test suite.

---

## 6.3 Add `tests/test_dependency_contract.py`

Recommended new focused integration test module.

Responsibilities:

1. installed PyKokoro is inside `>=0.8.3,<0.9`;
2. installed kokorog2p is inside `>=0.8.0,<0.9`;
3. ordinary structured written source is accepted by the PyKokoro/kokorog2p preparation
   boundary without ONNX inference;
4. TTSForge does not need to pre-expand these forms itself.

Example structure:

```python
from importlib.metadata import version

from packaging.specifiers import SpecifierSet
from packaging.version import Version

def test_supported_dependency_versions_are_installed():
    assert Version(version("pykokoro")) in SpecifierSet(">=0.8.3,<0.9")
    assert Version(version("kokorog2p")) in SpecifierSet(">=0.8.0,<0.9")
```

Functional boundary test can use the same representative class of source that upstream
0.8.3 tests:

```text
Dr. Smith will see you at 10:30 on 05/20/2023.
The box weighs 5 kg and costs $10.99.
```

Do not make TTSForge assert every English rendering phrase from Spokenform. That belongs
upstream.

For TTSForge, assert the integration invariants:

- call succeeds;
- phonemes/tokens are produced;
- no raw-digit failure leaks from preparation;
- no unexpected `[SPOKENFORM]` warning is emitted for the supported representative
  input.

---

## 6.4 `tests/test_resume_integrity.py`

Current test:

```python
def test_renderer_contract_uses_pykokoro_081_and_rejects_old_identity():
    contract = renderer_contract_payload()
    assert contract["pykokoro"] == "0.8.1"
    assert contract["schema"] == 2
```

Replace with a 0.8.3/0.8.0 contract test:

```python
def test_renderer_contract_uses_pykokoro_083_and_kokorog2p_080():
    contract = renderer_contract_payload()
    assert contract["schema"] == 3
    assert contract["pykokoro"] == "0.8.3"
    assert contract["kokorog2p"] == "0.8.0"
```

Add a separate resume migration regression.

Pseudo-test:

```python
from copy import deepcopy

def test_schema7_resume_rejects_pre_spokenform_renderer_contract_without_corrupting_state():
    converter = TTSConverter(ConversionOptions(title="Book"))
    current = converter._generation_identity()

    saved_payload = deepcopy(current.payload)
    renderer = saved_payload["ssmd_policy"]["renderer_contract"]
    renderer["schema"] = 2
    renderer["pykokoro"] = "0.8.1"
    renderer.pop("kokorog2p", None)

    saved_fingerprint = generation_fingerprint(saved_payload)

    state = ConversionState(
        version=7,
        source_hash="source",
        source_selection=[],
        onnx_provider="cpu",
        generation_identity_schema=GENERATION_IDENTITY_SCHEMA,
        generation_identity=saved_payload,
        generation_fingerprint=saved_fingerprint,
    )

    validation = converter._resume_state_matches(
        state,
        [],
        "source",
        current,
        Path("."),
    )

    assert validation.reason == "generation-fingerprint-changed"
    paths = {difference.path for difference in validation.differences}
    assert "ssmd_policy.renderer_contract.pykokoro" in paths
    assert "ssmd_policy.renderer_contract.kokorog2p" in paths
```

The exact set may also include the renderer schema path.

Critical assertion:

```python
assert validation.reason != "generation-identity-corrupt"
```

---

## 6.5 `tests/test_resume_identity.py`

Keep deterministic identity behavior.

Add a small assertion proving the current identity contains the new renderer contract:

```python
identity = _identity(ConversionOptions(conversion_unit="paragraph"))
contract = identity.payload["ssmd_policy"]["renderer_contract"]

assert contract["schema"] == 3
assert contract["pykokoro"] == "0.8.3"
assert contract["kokorog2p"] == "0.8.0"
```

Do not change `GENERATION_IDENTITY_SCHEMA` unless a separate migration is implemented.

---

## 6.6 `tests/test_name_extractor.py`

Add the direct kokorog2p regression described above.

This test currently does not exercise the direct phonemization dependency even though
production code imports it.

---

## 6.7 Vocabulary tests

Add or extend tests to exercise the TTSForge compatibility wrapper against kokorog2p
0.8.0.

Minimum useful coverage:

```text
load_vocab()
get_vocab_info()
encode/decode round trip or basic callability
validate_for_kokoro/filter_for_kokoro importability
```

---

# 7. CI review

## Current weakness

`.github/workflows/tests.yml` installs:

```bash
pip install -e .
pip install -r requirements-test.txt
pytest
```

That validates only the dependency versions selected by pip at test time.

It does **not** prove that the declared lower bounds work.

For a release whose main purpose is raising dependency minimums, that is insufficient.

---

## 7.1 Keep the normal OS/Python matrix

Continue the existing broad matrix across:

```text
Ubuntu
Windows
macOS

Python 3.10
3.11
3.12
3.13
```

assuming those remain the project's supported versions.

---

## 7.2 Add a dedicated minimum-dependency job

Use one deterministic Linux job, preferably Python 3.10 because it is the declared
minimum Python.

Concept:

```yaml
minimum-dependencies:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@<pinned-maintained-version>
    - uses: actions/setup-python@<pinned-maintained-version>
      with:
        python-version: "3.10"

    - run: |
        sudo apt-get update
        sudo apt-get install -y espeak-ng ffmpeg

    - run: |
        python -m pip install --upgrade pip
        python -m pip install \
          "kokorog2p[espeak,en]==0.8.0" \
          "pykokoro[cpu]==0.8.3"
        python -m pip install -e ".[dev]"

    - run: |
        python - <<'PY'
        from importlib.metadata import version
        assert version("kokorog2p") == "0.8.0"
        assert version("pykokoro") == "0.8.3"
        print("kokorog2p", version("kokorog2p"))
        print("pykokoro", version("pykokoro"))
        PY

    - run: |
        pytest -q \
          tests/test_packaging.py \
          tests/test_dependency_contract.py \
          tests/test_pykokoro_unit_contract.py \
          tests/test_kokoro_runner.py \
          tests/test_name_extractor.py \
          tests/test_resume_identity.py \
          tests/test_resume_integrity.py
```

Then run the full suite if runtime remains reasonable.

### Important

Do not add this job until the exact releases are installable from the target package
index, or temporarily point a pre-release integration branch at the intended artifact
source. The public release branch must eventually prove installation from the same
public index as end users.

---

## 7.3 Stop using floating `@master` GitHub Actions references

The current workflow uses floating `actions/checkout@master` and
`actions/setup-python@master`.

For release reproducibility, use the repository's accepted maintained major-version or
commit-pinning policy rather than floating `master`.

This is not caused by PyKokoro 0.8.3, but it is a worthwhile release-hardening cleanup
discovered during the CI review.

---

## 7.4 Consider running on pull requests

Current workflow trigger is push-only.

Recommended:

```yaml
on:
  push:
  pull_request:
```

Treat this as CI hardening rather than a blocker if project policy intentionally uses
another PR gate.

---

# 8. Documentation changes

## 8.1 `README.md`

Current text says:

```text
TTSForge requires released PyKokoro >=0.8.2,<0.9.
```

Update to:

```text
TTSForge requires PyKokoro >=0.8.3,<0.9 and kokorog2p >=0.8.0,<0.9.
```

Because TTSForge directly declares the kokorog2p extra, it is better to be precise:

```text
TTSForge uses pykokoro[cpu]>=0.8.3,<0.9 and
kokorog2p[espeak,en]>=0.8.0,<0.9.
```

Add a short behavior note:

> With the 0.8.3/0.8.0 stack, ordinary written forms such as supported dates, times,
> measurements, currency, ordinals, and abbreviations are prepared for speech by
> kokorog2p before G2P. TTSForge does not duplicate that normalization.

Also say:

> Explicit SSMD `say-as` remains an author override and is not replaced by automatic
> written-to-spoken preparation.

Do not overpromise identical normalization across every language. Link/document the
supported-language boundary rather than inventing a TTSForge-specific compatibility
list.

---

## 8.2 `docs/installation.md`

Change:

```text
PyKokoro >=0.8.2,<0.9
SSMD >=0.8.0,<0.9
```

to:

```text
PyKokoro >=0.8.3,<0.9
kokorog2p >=0.8.0,<0.9
SSMD >=0.8.1,<0.9
```

Explain the ownership chain:

```text
TTSForge -> PyKokoro -> kokorog2p -> Spokenform/abbr2words
```

State explicitly:

- users should not install `spokenform` separately for TTSForge;
- the compatible kokorog2p release owns its Spokenform/abbr2words constraints;
- the public dependency versions must be available before installing TTSForge 0.3.4.

---

## 8.3 `docs/ssmd.md`

The current document correctly describes explicit `say-as`, substitution, phoneme,
prosody, and other SSMD controls.

Add a subsection such as:

```markdown
### Automatic written-to-spoken preparation vs explicit say-as
```

Explain:

- ordinary unannotated text flows through the PyKokoro/kokorog2p 0.8.x preparation
  boundary;
- supported structured forms may be converted to speakable forms automatically;
- `[100]{as="cardinal"}` and other SSMD `say-as` annotations remain explicit document
  semantics;
- TTSForge does not rewrite source SSMD into new automatic annotations;
- explicit author intent must win over implicit normalization according to the upstream
  renderer contract.

This distinction prevents users from assuming they must manually annotate every
date/measurement after the upgrade.

---

## 8.4 `docs/testing.md`

Add the new dependency contract suite and the exact minimum-version CI purpose.

Suggested section:

```markdown
## Minimum dependency contract

TTSForge's release CI separately installs:

- PyKokoro 0.8.3
- kokorog2p 0.8.0

This job proves the lower bounds declared by the package, while the normal matrix
continues to test currently resolved compatible versions.
```

Update any stale paragraph-schema wording if the renderer contract tests change.

---

## 8.5 `docs/changelog.md`

Do **not** hand-edit the generated changelog.

The file explicitly says it is generated by releaseledger.

Create/update 0.3.4 releaseledger entries and regenerate the changelog through the
repository's releaseledger workflow.

Suggested public entries:

### Changed

```text
Changed the minimum TTS stack to PyKokoro 0.8.3 and kokorog2p 0.8.0, enabling the new source-aware written-to-spoken preparation boundary.
```

### Fixed

```text
Fixed resumable conversion compatibility so audio generated under the older PyKokoro/kokorog2p semantic contract is not silently mixed with the new renderer contract.
```

### Documentation

```text
Documented automatic written-to-spoken preparation, explicit SSMD say-as ownership, and the new minimum dependency versions.
```

---

# 9. Releaseledger work

The repository already contains:

```text
release 0.3.4
status: planned
previous_version: 0.3.3
```

Use that release object.

Do not create a duplicate release.

Add accepted entries for the actual implementation commits, then regenerate
`docs/changelog.md`.

Before finalizing:

- audit the commit range from 0.3.3 to the 0.3.4 release head;
- associate dependency, resume, test/CI, and documentation commits with release entries;
- ensure no unrelated public changes are left unclassified;
- finalize only after the exact minimum dependency install test succeeds.

---

# 10. Recommended implementation order

## Phase 1 — package metadata

1. Update `pyproject.toml`:

   - PyKokoro 0.8.3 floor
   - direct kokorog2p 0.8.0 floor
   - SSMD 0.8.1 floor
   - TTSForge fallback 0.3.4

2. Update packaging tests.

3. Remove/redesign the brittle sibling-PyKokoro fallback assertion.

## Phase 2 — semantic resume contract

1. Update `PYKOKORO_RENDERER_VERSION` to `0.8.3`.
2. Add kokorog2p 0.8.0 semantic contract.
3. Bump renderer contract schema to 3.
4. Keep generation identity schema at 2.
5. Add old-contract resume regression.

## Phase 3 — runtime messages and direct boundaries

1. Update stale PyKokoro 0.8.2 error strings.
2. Add name-extractor direct kokorog2p test.
3. Add vocabulary compatibility test.
4. Add focused dependency/Spokenform integration test.

## Phase 4 — CI

1. Add minimum-dependency job.
2. Assert installed versions are exactly 0.8.3/0.8.0 in that job.
3. Keep normal latest-compatible matrix.
4. Replace floating action `master` references according to repository pinning policy.
5. Optionally add PR trigger.

## Phase 5 — documentation

Update:

```text
README.md
docs/installation.md
docs/ssmd.md
docs/testing.md
```

Create releaseledger entries and regenerate:

```text
docs/changelog.md
```

## Phase 6 — dependency publication gate

Publish/verify:

```text
kokorog2p 0.8.0
PyKokoro 0.8.3
```

Then test a clean environment using only the public target index.

## Phase 7 — TTSForge 0.3.4 release

Only after all gates pass:

- build;
- inspect wheel metadata;
- run full test suite;
- run lint/type/pre-commit policy;
- run docs build;
- finalize releaseledger;
- tag/publish 0.3.4.

---

# 11. Minimum-version release validation

Once upstream packages are published, create a clean environment.

Example:

```bash
python3.10 -m venv .venv-min
. .venv-min/bin/activate

python -m pip install --upgrade pip setuptools wheel

python -m pip install \
  "kokorog2p[espeak,en]==0.8.0" \
  "pykokoro[cpu]==0.8.3"

python -m pip install -e ".[dev]"
```

Verify the resolver did not replace the minimum versions:

```bash
python - <<'PY'
from importlib.metadata import version

assert version("kokorog2p") == "0.8.0", version("kokorog2p")
assert version("pykokoro") == "0.8.3", version("pykokoro")

print("kokorog2p:", version("kokorog2p"))
print("pykokoro:", version("pykokoro"))
PY
```

Run focused release-contract tests:

```bash
pytest -q \
  tests/test_packaging.py \
  tests/test_dependency_contract.py \
  tests/test_pykokoro_unit_contract.py \
  tests/test_kokoro_runner.py \
  tests/test_name_extractor.py \
  tests/test_resume_identity.py \
  tests/test_resume_integrity.py \
  tests/test_phoneme_dictionary.py \
  tests/test_tokenizer.py
```

Run paragraph/resume tests:

```bash
pytest -q \
  tests/test_conversion_unit_cli.py \
  tests/test_paragraph_filenames.py \
  tests/test_paragraph_state.py \
  tests/test_paragraph_rendering.py \
  tests/test_paragraph_audio_parity.py \
  tests/test_paragraph_merge.py \
  tests/test_paragraph_manifest.py \
  tests/test_convert_resume_cli.py
```

Then run the full maintained policy:

```bash
pytest
tox
pre-commit run --all-files
```

If the repository invokes Ruff/mypy separately in its normal release process, run those
exact maintained commands as well.

---

# 12. Functional smoke tests

The release should include at least one non-ONNX dependency smoke test and one real
synthesis smoke test.

## Written-to-spoken smoke source

Use representative ordinary text:

```text
Dr. Smith will see you at 10:30 on 05/20/2023.
The box weighs 5 kg and costs $10.99.
The temperature is 98.6°F.
She finished in 1st place.
```

Expected properties:

- conversion does not require TTSForge-side manual expansion;
- kokorog2p produces a valid prepared/phonemized result;
- PyKokoro accepts the result without unexpected Spokenform warnings;
- a normal TTSForge `sample` or short conversion completes after model setup.

Do not turn the exact English wording into a large TTSForge-owned golden corpus. The
exact language normalization corpus belongs to kokorog2p.

## SSMD override smoke source

Also test explicit author intent, for example:

```text
The identifier is [100]{as="digits"}.
```

Verify the explicit SSMD semantics remain active and are not incorrectly replaced by
automatic ordinary-text preparation.

---

# 13. Build and wheel inspection

Install build tooling if not already available:

```bash
python -m pip install build twine
```

Clean old artifacts:

```bash
rm -rf build dist *.egg-info wheel-smoke
```

Build:

```bash
python -m build
```

Validate:

```bash
python -m twine check dist/*
```

Inspect wheel metadata and verify the final package advertises all of:

```text
Requires-Dist: pykokoro[cpu] (>=0.8.3,<0.9)
Requires-Dist: kokorog2p[espeak,en] (>=0.8.0,<0.9)
Requires-Dist: ssmd (>=0.8.1,<0.9)
Requires-Dist: phrasplit (>=0.3.4,<0.4)
```

Exact METADATA formatting can differ by build backend; test the semantic requirement
rather than spacing.

Verify the wheel does not report an old or zero fallback version.

Expected release version:

```text
0.3.4
```

---

# 14. Clean-install test

After building, test the wheel rather than only the editable checkout.

Example:

```bash
python3.10 -m venv .venv-wheel
. .venv-wheel/bin/activate

python -m pip install --upgrade pip
python -m pip install dist/ttsforge-0.3.4-*.whl

python - <<'PY'
from importlib.metadata import version
print("ttsforge:", version("ttsforge"))
print("pykokoro:", version("pykokoro"))
print("kokorog2p:", version("kokorog2p"))
PY

ttsforge --version
ttsforge --help
```

Then run a lightweight command that does not require model inference, followed by a real
sample conversion in the release environment.

---

# 15. Review findings classified by priority

## P0 — release must not proceed without these

- publish/verify kokorog2p 0.8.0 on the target index;
- publish/verify PyKokoro 0.8.3 on the target index;
- bump TTSForge PyKokoro floor to 0.8.3;
- declare kokorog2p 0.8.0 directly;
- align SSMD to 0.8.1;
- update stale semantic renderer contract;
- ensure old semantic-contract resumes are rejected safely;
- update stale packaging tests;
- prove exact minimum versions in CI.

## P1 — should be in 0.3.4

- update all README/docs version references;
- document automatic written-to-spoken vs explicit SSMD `say-as`;
- update stale runtime installation messages;
- exercise direct `name_extractor` kokorog2p use;
- exercise TTSForge vocabulary wrapper against kokorog2p 0.8.0;
- update `setuptools_scm` fallback to 0.3.4;
- regenerate releaseledger changelog;
- inspect built wheel metadata.

## P2 — release hardening discovered during review

- replace floating GitHub Action `@master` references;
- add pull-request CI if not covered elsewhere;
- simplify legacy `requirements-test.txt` if obsolete `nose`/`flake8` entries are no
  longer part of maintained tooling;
- consider centralizing supported dependency specifier constants so error strings cannot
  drift from package metadata.

Do not let P2 cleanup expand the release enough to delay the P0/P1 compatibility work.

---

# 16. Things the coding agent should explicitly avoid

1. **Do not implement another TTSForge text-normalization layer.** The new automatic
   written-to-spoken behavior belongs to kokorog2p.

2. **Do not add direct TTSForge dependencies on `spokenform` or `abbr2words`.** Those
   belong to kokorog2p.

3. **Do not bump `GENERATION_IDENTITY_SCHEMA` merely because dependency semantics
   changed.** That currently makes older valid identities look corrupt.

4. **Do not fingerprint every installed patch version automatically.** Use the explicit
   semantic renderer contract unless the project intentionally changes its resume
   policy.

5. **Do not rely on the normal pip-resolved CI matrix to prove minimum versions.**
   Install exact minimums in a dedicated job.

6. **Do not rely on the sibling-PyKokoro checkout test as a release gate.** It skips in
   ordinary standalone TTSForge CI.

7. **Do not hand-edit `docs/changelog.md`.** It is releaseledger-generated.

8. **Do not publish TTSForge 0.3.4 before the exact upstream versions are installable
   from the target package index.**

---

# 17. Suggested patch outline

The implementation should roughly touch:

```text
pyproject.toml

ttsforge/kokoro_runner.py
ttsforge/render_units.py

tests/test_packaging.py
tests/test_resume_identity.py
tests/test_resume_integrity.py
tests/test_name_extractor.py
tests/test_dependency_contract.py          # new, recommended
tests/<vocab-contract-test>.py              # new or extend existing tokenizer/vocab tests

.github/workflows/tests.yml

README.md
docs/installation.md
docs/ssmd.md
docs/testing.md

.ledger/releaseledger/.../releases/0.3.4/...  # through releaseledger workflow
docs/changelog.md                              # generated
```

No large rewrite of:

```text
ttsforge/conversion.py
ttsforge/kokoro_runner.py pipeline wiring
ttsforge/vocab/__init__.py
```

is indicated by the inspected API compatibility, beyond the specific contract/message
changes described above.

---

# 18. Acceptance criteria

The coding task is complete only when all of the following are true.

## Package metadata

- [ ] TTSForge declares `pykokoro[cpu]>=0.8.3,<0.9`.
- [ ] TTSForge directly declares `kokorog2p[espeak,en]>=0.8.0,<0.9`.
- [ ] TTSForge declares `ssmd>=0.8.1,<0.9`.
- [ ] TTSForge retains `phrasplit>=0.3.4,<0.4`.
- [ ] TTSForge fallback version is appropriate for 0.3.4.
- [ ] Built wheel METADATA contains the intended floors.

## Runtime/API

- [ ] All currently consumed PyKokoro public interfaces import under 0.8.3.
- [ ] TTSForge vocabulary compatibility imports under kokorog2p 0.8.0.
- [ ] `generate_phoneme_suggestions()` works with kokorog2p 0.8.0.
- [ ] stale `pykokoro>=0.8.2` runtime guidance is gone.

## Written-to-spoken behavior

- [ ] representative structured ordinary text reaches kokorog2p/PyKokoro successfully.
- [ ] TTSForge does not duplicate Spokenform normalization.
- [ ] explicit SSMD `say-as` remains an explicit override.

## Resume safety

- [ ] renderer contract schema is bumped.
- [ ] renderer contract names PyKokoro 0.8.3.
- [ ] renderer contract names kokorog2p 0.8.0.
- [ ] `GENERATION_IDENTITY_SCHEMA` stays at 2 unless a real migration is added.
- [ ] pre-upgrade schema-2 identities are not labeled corrupt.
- [ ] pre-upgrade generated audio cannot silently resume under the new semantic
      contract.
- [ ] mismatch diagnostics remain field-level and actionable.

## Tests/CI

- [ ] stale packaging assertions are updated.
- [ ] sibling-upstream metadata coupling is removed or intentionally updated.
- [ ] minimum-version CI installs exact 0.8.3/0.8.0.
- [ ] normal matrix still tests current compatible dependencies.
- [ ] focused dependency/resume tests pass.
- [ ] paragraph/resume regression suite passes.
- [ ] full pytest suite passes.
- [ ] maintained coverage gates pass.
- [ ] pre-commit/lint/type checks pass according to repository policy.

## Docs/release

- [ ] README states new floors.
- [ ] installation docs state new floors and ownership boundary.
- [ ] SSMD docs distinguish automatic preparation from explicit `say-as`.
- [ ] testing docs explain minimum-version CI.
- [ ] 0.3.4 releaseledger entries describe the change.
- [ ] changelog is regenerated, not manually edited.
- [ ] kokorog2p 0.8.0 is publicly installable before TTSForge release.
- [ ] PyKokoro 0.8.3 is publicly installable before TTSForge release.
- [ ] clean wheel installation succeeds.

---

# 19. Suggested release note for 0.3.4

## Changed

TTSForge now requires PyKokoro 0.8.3 and kokorog2p 0.8.0 as the minimum supported
generation stack. The updated stack uses kokorog2p's source-aware written-to-spoken
preparation for supported ordinary forms such as dates, times, measurements, currency,
ordinals, and abbreviations while preserving TTSForge's existing SSMD and audiobook
orchestration boundaries.

## Fixed

Resumable conversion now treats the PyKokoro 0.8.3 / kokorog2p 0.8.0 renderer semantics
as a new generation contract, preventing completed audio generated under the older
renderer contract from being silently mixed with newly generated units.

## Documentation

Documentation now distinguishes automatic written-to-spoken preparation from explicit
SSMD `say-as` annotations and documents the new minimum dependency versions and
minimum-version CI policy.

---

# 20. Final release decision

**Target release:** `ttsforge 0.3.4`

**Implementation readiness:** code changes are well scoped; no broad PyKokoro API
migration was identified.

**Publication readiness at audit time:** **not yet ready**, because the required public
upstream artifacts were not yet available on PyPI on 2026-08-15.

The correct completion sequence is:

```text
finish + release kokorog2p 0.8.0
            |
            v
finish + release PyKokoro 0.8.3
            |
            v
run exact-minimum TTSForge CI
            |
            v
complete TTSForge 0.3.4 code/docs/releaseledger
            |
            v
build + clean-install + full test
            |
            v
publish TTSForge 0.3.4
```
