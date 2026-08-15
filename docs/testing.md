# Testing and Coverage

Run the normal test suite with:

```bash
pytest
```

Paragraph conversion has focused contract coverage:

```bash
pytest -q tests/test_pykokoro_unit_contract.py tests/test_conversion_unit_cli.py \
  tests/test_paragraph_filenames.py tests/test_paragraph_state.py \
  tests/test_paragraph_rendering.py tests/test_paragraph_audio_parity.py \
  tests/test_paragraph_merge.py tests/test_paragraph_manifest.py
```

These tests cover public PyKokoro streaming, schema-6 seed persistence and explicit
schema-5 paragraph rejection, atomic output and ownership, unit resume boundaries,
filename ordering, timing parity, no-gap merging, strict CLI mismatch handling, and
merge-only recovery. The main regression test models a changed stochastic descriptor
hash and verifies that a saved prefix is not rendered again.

## Minimum dependency contract

Release CI separately installs the exact lower-bound generation stack:

- PyKokoro 0.8.3
- kokorog2p 0.8.0

The minimum-dependency job proves that the package's declared lower bounds install and
that representative written-to-spoken source reaches the upstream preparation/G2P
boundary. The normal OS/Python matrix continues to test currently resolved compatible
dependencies.

The focused local equivalent is:

```bash
pytest -q tests/test_packaging.py tests/test_dependency_contract.py \
  tests/test_pykokoro_unit_contract.py tests/test_name_extractor.py \
  tests/test_resume_identity.py tests/test_resume_integrity.py
```

The maintained coverage policy is staged so high-risk code has explicit gates while the
repository-wide target can be raised as the large CLI modules are decomposed:

- repository branch coverage: 55% minimum;
- `ttsforge/audio_player.py`: 80% minimum;
- `ttsforge/audio_merge.py`: 75% minimum;
- changed lines: 85% minimum;
- changed resume/state lines are expected to meet the same 85% changed-line gate, which
  is stricter than the initial 80% target.

The complete policy is wired into tox:

```bash
tox
```

The final changed-line check compares `coverage.xml` with `origin/main` using
`diff-cover`. A local checkout without that remote can run the first three coverage
commands directly and use an appropriate local base branch for the final comparison.
