# Configuration

TTSForge does not maintain a separate synthesis or engine configuration. Its `config`
commands call Readio's public configuration service, so the active path, settings,
language profiles, and engine behavior are owned by Readio.

## Inspect and initialize

```bash
ttsforge config path
ttsforge config show
ttsforge config init
ttsforge config languages
ttsforge config language en-us
```

`path` prints the active configuration file. `show` prints its persisted settings.
`init` asks Readio to initialize configuration and standard directories. `languages`
lists configured language profiles; `language LOCALE` resolves the exact or
base-language profile.

Do not assume a platform-specific config location. Ask Readio with
`ttsforge config path`.

## Set a Readio setting

Use a dotted Readio key and one value:

```bash
ttsforge config set reader.voice af_heart
ttsforge config set reader.lang en-us
ttsforge config set reader.speed 1.1
```

Values that are valid JSON are parsed as JSON, so numbers, booleans, arrays, and objects
retain their types. Other values are stored as text. To target an alternate file, use
`--path` with `show` or `set`:

```bash
ttsforge config show --path ./readio.toml
ttsforge config set reader.speed 1.0 --path ./readio.toml
```

The accepted keys and validation rules belong to Readio. For the full setting
model—including reader defaults, language profiles, engine-specific settings, and
project-local behavior—use
[Readio's configuration documentation](https://github.com/buchwandler/readio/blob/main/docs/index.md).

## Command-line overrides and projects

`convert` and `preview` accept per-operation options such as `--voice`, `--language`,
`--engine`, `--model`, `--model-source`, `--quality`, `--speed`, and `--target-lufs`.
These are mapped to Readio public request types; they do not create a second TTSForge
config schema. Persistent project state and Readio's rules for effective settings
determine reuse. Refer to the
[Readio project guide](https://github.com/buchwandler/readio/blob/main/docs/projects.md)
before relying on project/global setting precedence.

## Migrating old settings

Former TTSForge-specific keys and config files are not automatically imported. Review
the old values and set only their current Readio equivalents. TTSForge no longer accepts
backend controls for PyKokoro internals, phoneme dictionaries, renderer pause settings,
or TTSForge-specific output filename templates. See the
[migration guide](migration-readio.md).

## Diagnose configuration and engine setup

```bash
ttsforge config show
ttsforge engines
ttsforge models
ttsforge doctor
```

`doctor` is the Readio diagnostics service. It reports the active Readio
version/configuration, available engines and dependencies, output formats, and standard
paths. Install and configure engines using Readio's documented extras and settings;
TTSForge does not install engine runtimes itself.
