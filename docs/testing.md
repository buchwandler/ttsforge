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

These tests cover public PyKokoro streaming, schema-5 migration, atomic output and
ownership, unit resume boundaries, filename ordering, timing parity, no-gap merging,
and merge-only recovery.

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
