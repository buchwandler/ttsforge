# Testing and Coverage

Run the normal test suite with:

```bash
pytest
```

The maintained coverage policy is staged so high-risk code has explicit gates
while the repository-wide target can be raised as the large CLI modules are
decomposed:

- repository branch coverage: 55% minimum;
- `ttsforge/audio_player.py`: 80% minimum;
- `ttsforge/audio_merge.py`: 75% minimum;
- changed lines: 85% minimum;
- changed resume/state lines are expected to meet the same 85% changed-line
  gate, which is stricter than the initial 80% target.

The complete policy is wired into tox:

```bash
tox
```

The final changed-line check compares `coverage.xml` with
`origin/main` using `diff-cover`. A local checkout without that remote can
run the first three coverage commands directly and use an appropriate local
base branch for the final comparison.
