"""Tests for ttsforge.conversion module."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
import soundfile as sf

from ttsforge.conversion import (
    SPLIT_MODES,
    Chapter,
    ChapterState,
    ConversionOptions,
    ConversionProgress,
    ConversionResult,
    ConversionState,
    RenderedChapter,
    TTSConverter,
    _hash_content,
    _hash_file,
    detect_language_from_iso,
    get_default_voice_for_language,
    get_voice_language,
)


class TestChapter:
    """Tests for Chapter dataclass."""

    def test_basic_creation(self):
        """Should create chapter with required fields."""
        chapter = Chapter(title="Chapter 1", content="Hello world", index=0)
        assert chapter.title == "Chapter 1"
        assert chapter.content == "Hello world"
        assert chapter.index == 0

    def test_char_count_property(self):
        """char_count should return length of content."""
        chapter = Chapter(title="Test", content="Hello", index=0)
        assert chapter.char_count == 5

    def test_empty_content(self):
        """Should handle empty content."""
        chapter = Chapter(title="Empty", content="", index=0)
        assert chapter.char_count == 0

    def test_unicode_content(self):
        """Should handle unicode content."""
        chapter = Chapter(title="Unicode", content="Hello \u4e16\u754c", index=0)
        assert chapter.char_count == 8  # "Hello " + 2 Chinese chars


class TestConversionProgress:
    """Tests for ConversionProgress dataclass."""

    def test_percent_zero_total(self):
        """Percent should be 0 when total_chars is 0."""
        progress = ConversionProgress(total_chars=0, chars_processed=0)
        assert progress.percent == 0

    def test_percent_calculation(self):
        """Percent should calculate correctly."""
        progress = ConversionProgress(total_chars=100, chars_processed=50)
        assert progress.percent == 50

    def test_percent_caps_at_99(self):
        """Percent should cap at 99."""
        progress = ConversionProgress(total_chars=100, chars_processed=100)
        assert progress.percent == 99

    def test_etr_formatted(self):
        """etr_formatted should format correctly."""
        progress = ConversionProgress(estimated_remaining=3661)
        assert progress.etr_formatted == "01:01:01"


class TestConversionResult:
    """Tests for ConversionResult dataclass."""

    def test_success_result(self):
        """Should create successful result."""
        result = ConversionResult(success=True, output_path=Path("/tmp/out.wav"))
        assert result.success is True
        assert result.output_path == Path("/tmp/out.wav")
        assert result.error_message is None

    def test_failure_result(self):
        """Should create failure result."""
        result = ConversionResult(success=False, error_message="Something went wrong")
        assert result.success is False
        assert result.error_message == "Something went wrong"


class TestRenderedChapter:
    def test_has_only_lightweight_render_data(self, tmp_path):
        rendered = RenderedChapter(
            duration=1.0,
            rendered_path=tmp_path / "chapter.wav",
            sample_rate=24000,
            diagnostics=(),
            markers=[],
            document_metadata={"title": "Chapter"},
        )

        assert rendered.duration == 1.0
        assert not hasattr(rendered, "audio")
        assert not hasattr(rendered, "result")


class TestChapterState:
    """Tests for ChapterState dataclass."""

    def test_basic_creation(self):
        """Should create chapter state."""
        state = ChapterState(
            index=0,
            title="Chapter 1",
            content_hash="abc123",
            completed=False,
        )
        assert state.index == 0
        assert state.title == "Chapter 1"
        assert state.content_hash == "abc123"
        assert state.completed is False

    def test_completed_state(self):
        """Should track completed state."""
        state = ChapterState(
            index=0,
            title="Chapter 1",
            content_hash="abc123",
            completed=True,
            audio_file="chapter_000.wav",
            duration=120.5,
        )
        assert state.completed is True
        assert state.audio_file == "chapter_000.wav"
        assert state.duration == 120.5


class TestConversionState:
    """Tests for ConversionState dataclass."""

    def test_default_values(self):
        """Should have correct defaults."""
        state = ConversionState()
        assert state.version == 1
        assert state.chapters == []
        assert state.voice == ""
        assert state.language == ""

    def test_custom_values(self):
        """Should accept custom values."""
        state = ConversionState(
            source_hash="abc123",
            voice="af_bella",
            language="a",
            speed=1.2,
        )
        assert state.source_hash == "abc123"
        assert state.voice == "af_bella"
        assert state.language == "a"
        assert state.speed == 1.2

    def test_save_and_load(self):
        """Should save and load state correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            # Create and save state
            original = ConversionState(
                source_hash="test123",
                voice="am_adam",
                language="a",
                speed=1.2,
                split_mode="sentence",
                chapters=[
                    ChapterState(
                        index=0, title="Ch 1", content_hash="hash1", completed=True
                    ),
                    ChapterState(
                        index=1, title="Ch 2", content_hash="hash2", completed=False
                    ),
                ],
            )
            original.save(state_file)

            # Load and verify
            loaded = ConversionState.load(state_file)
            assert loaded is not None
            assert loaded.source_hash == "test123"
            assert loaded.voice == "am_adam"
            assert loaded.speed == 1.2
            assert len(loaded.chapters) == 2
            assert loaded.chapters[0].completed is True

    def test_load_nonexistent_file(self):
        """Should return None for nonexistent file."""
        result = ConversionState.load(Path("/nonexistent/state.json"))
        assert result is None

    def test_get_completed_count(self):
        """Should count completed chapters."""
        state = ConversionState(
            chapters=[
                ChapterState(index=0, title="Ch 1", content_hash="h1", completed=True),
                ChapterState(index=1, title="Ch 2", content_hash="h2", completed=False),
                ChapterState(index=2, title="Ch 3", content_hash="h3", completed=True),
            ]
        )
        assert state.get_completed_count() == 2

    def test_get_next_incomplete_index(self):
        """Should return first incomplete chapter index."""
        state = ConversionState(
            chapters=[
                ChapterState(index=0, title="Ch 1", content_hash="h1", completed=True),
                ChapterState(index=1, title="Ch 2", content_hash="h2", completed=False),
                ChapterState(index=2, title="Ch 3", content_hash="h3", completed=False),
            ]
        )
        assert state.get_next_incomplete_index() == 1


class TestConversionOptions:
    """Tests for ConversionOptions dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        options = ConversionOptions()
        assert options.voice == "af_bella"
        assert options.language == "a"
        assert options.speed == 1.0
        assert options.output_format == "m4b"
        assert options.use_gpu is False  # ONNX default is CPU
        assert options.effective_onnx_provider() == "cpu"

    def test_custom_values(self):
        """Should accept custom values."""
        options = ConversionOptions(
            voice="am_adam",
            language="b",
            speed=1.5,
            output_format="wav",
            use_gpu=True,
        )
        assert options.voice == "am_adam"
        assert options.language == "b"
        assert options.speed == 1.5
        assert options.output_format == "wav"
        assert options.use_gpu is True
        assert options.effective_onnx_provider() == "auto"

    def test_explicit_provider_is_preserved(self):
        options = ConversionOptions(onnx_provider="nnapi")
        assert options.effective_onnx_provider() == "nnapi"

    def test_split_mode_default(self):
        """split_mode should default to 'auto'."""
        options = ConversionOptions()
        assert options.split_mode == "auto"

    def test_resume_default(self):
        """resume should default to True."""
        options = ConversionOptions()
        assert options.resume is True

    def test_voice_blend_option(self):
        """Should accept voice_blend option."""
        options = ConversionOptions(voice_blend="af_nicole:50,am_michael:50")
        assert options.voice_blend == "af_nicole:50,am_michael:50"

    def test_voice_database_option(self):
        """Should accept voice_database option."""
        from pathlib import Path

        options = ConversionOptions(voice_database=Path("/tmp/voices.db"))
        assert options.voice_database == Path("/tmp/voices.db")


class TestSplitModes:
    """Tests for SPLIT_MODES constant."""

    def test_expected_modes(self):
        """Should have expected split modes."""
        expected = {"auto", "line", "paragraph", "sentence", "clause"}
        assert set(SPLIT_MODES) == expected


class TestDetectLanguageFromIso:
    """Tests for detect_language_from_iso function."""

    def test_none_returns_default(self):
        """None should return 'a' (American English)."""
        assert detect_language_from_iso(None) == "a"

    def test_empty_returns_default(self):
        """Empty string should return 'a'."""
        assert detect_language_from_iso("") == "a"

    def test_english_codes(self):
        """English codes should map correctly."""
        assert detect_language_from_iso("en") == "a"
        assert detect_language_from_iso("en-US") == "a"
        assert detect_language_from_iso("en-GB") == "b"

    def test_case_insensitive(self):
        """Should be case insensitive."""
        assert detect_language_from_iso("EN") == "a"
        assert detect_language_from_iso("En-Us") == "a"
        assert detect_language_from_iso("EN-GB") == "b"

    def test_other_languages(self):
        """Other languages should map correctly."""
        assert detect_language_from_iso("es") == "e"
        assert detect_language_from_iso("fr") == "f"
        assert detect_language_from_iso("ja") == "j"
        assert detect_language_from_iso("zh") == "z"

    def test_unknown_returns_default(self):
        """Unknown codes should return 'a'."""
        assert detect_language_from_iso("xx") == "a"
        assert detect_language_from_iso("unknown") == "a"

    def test_whitespace_handling(self):
        """Should handle whitespace."""
        assert detect_language_from_iso(" en ") == "a"
        assert detect_language_from_iso("  fr  ") == "f"


class TestGetVoiceLanguage:
    """Tests for get_voice_language function."""

    def test_american_voices(self):
        """American voices should return 'a'."""
        assert get_voice_language("af_bella") == "a"
        assert get_voice_language("am_adam") == "a"

    def test_british_voices(self):
        """British voices should return 'b'."""
        assert get_voice_language("bf_emma") == "b"
        assert get_voice_language("bm_george") == "b"

    def test_other_language_voices(self):
        """Other language voices should map correctly."""
        assert get_voice_language("ef_dora") == "e"  # Spanish
        assert get_voice_language("ff_siwis") == "f"  # French
        assert get_voice_language("jf_alpha") == "j"  # Japanese
        assert get_voice_language("zf_xiaoxiao") == "z"  # Chinese

    def test_short_string(self):
        """Short strings should return default 'a'."""
        assert get_voice_language("a") == "a"
        assert get_voice_language("") == "a"

    def test_unknown_prefix(self):
        """Unknown prefixes should return 'a'."""
        assert get_voice_language("xx_unknown") == "a"


class TestGetDefaultVoiceForLanguage:
    """Tests for get_default_voice_for_language function."""

    def test_american_english(self):
        """American English should return af_heart."""
        assert get_default_voice_for_language("a") == "af_heart"

    def test_british_english(self):
        """British English should return bf_emma."""
        assert get_default_voice_for_language("b") == "bf_emma"

    def test_other_languages(self):
        """Other languages should have default voices."""
        assert get_default_voice_for_language("e") == "ef_dora"
        assert get_default_voice_for_language("f") == "ff_siwis"
        assert get_default_voice_for_language("j") == "jf_alpha"

    def test_unknown_language(self):
        """Unknown language should return fallback."""
        assert get_default_voice_for_language("x") == "af_bella"


class TestHashFunctions:
    """Tests for hash functions."""

    def test_hash_content(self):
        """Should hash content consistently."""
        content = "Hello, World!"
        hash1 = _hash_content(content)
        hash2 = _hash_content(content)
        assert hash1 == hash2
        assert len(hash1) == 12  # First 12 chars of MD5

    def test_hash_content_different_inputs(self):
        """Different inputs should produce different hashes."""
        hash1 = _hash_content("Hello")
        hash2 = _hash_content("World")
        assert hash1 != hash2

    def test_hash_file(self):
        """Should hash file content."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Test content")
            f.flush()
            temp_path = Path(f.name)
        try:
            hash1 = _hash_file(temp_path)
            hash2 = _hash_file(temp_path)
            assert hash1 == hash2
            assert len(hash1) == 12  # First 12 chars of MD5
        finally:
            temp_path.unlink()

    def test_hash_file_different_content(self):
        """Different files should produce different hashes."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f1:
            f1.write("Content 1")
            f1.flush()
            temp_path1 = Path(f1.name)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f2:
            f2.write("Content 2")
            f2.flush()
            temp_path2 = Path(f2.name)
        try:
            hash1 = _hash_file(temp_path1)
            hash2 = _hash_file(temp_path2)
            assert hash1 != hash2
        finally:
            temp_path1.unlink()
            temp_path2.unlink()

    def test_hash_file_nonexistent(self):
        """Should return empty string for nonexistent file."""
        hash_result = _hash_file(Path("/nonexistent/file.txt"))
        assert hash_result == ""


class TestTTSConverterInit:
    """Tests for TTSConverter initialization (without actual TTS)."""

    def test_options_stored(self):
        """Options should be stored."""
        from ttsforge.conversion import TTSConverter

        options = ConversionOptions(voice="am_adam", speed=1.5)
        converter = TTSConverter(options)
        assert converter.options.voice == "am_adam"
        assert converter.options.speed == 1.5

    def test_callbacks_stored(self):
        """Callbacks should be stored."""
        from ttsforge.conversion import TTSConverter

        progress_cb = MagicMock()
        log_cb = MagicMock()
        options = ConversionOptions()
        converter = TTSConverter(
            options, progress_callback=progress_cb, log_callback=log_cb
        )
        assert converter.progress_callback is progress_cb
        assert converter.log_callback is log_cb

    def test_log_method(self):
        """log method should call log_callback."""
        from ttsforge.conversion import TTSConverter

        log_cb = MagicMock()
        options = ConversionOptions()
        converter = TTSConverter(options, log_callback=log_cb)
        converter.log("Test message", "info")
        log_cb.assert_called_once_with("Test message", "info")

    def test_cancel_method(self):
        """cancel method should set _cancelled flag."""
        from ttsforge.conversion import TTSConverter

        options = ConversionOptions()
        converter = TTSConverter(options)
        assert converter._cancelled is False
        converter.cancel()
        assert converter._cancelled is True

    def test_close_is_idempotent_and_detaches_runner(self):
        converter = TTSConverter(ConversionOptions())
        runner = MagicMock()
        converter._runner = runner

        converter.close()
        converter.close()

        runner.close.assert_called_once_with()
        assert converter._runner is None

    def test_context_manager_closes_runner(self):
        converter = TTSConverter(ConversionOptions())
        runner = MagicMock()
        converter._runner = runner

        with converter as active:
            assert active is converter

        runner.close.assert_called_once_with()

    def test_context_manager_closes_runner_on_exception(self):
        converter = TTSConverter(ConversionOptions())
        runner = MagicMock()
        converter._runner = runner

        with pytest.raises(RuntimeError, match="boom"):
            with converter:
                raise RuntimeError("boom")

        runner.close.assert_called_once_with()


class TestChapterRendering:
    @staticmethod
    def _converter(tmp_path):
        return TTSConverter(ConversionOptions(), log_callback=lambda *_args: None)

    @staticmethod
    def _result(release_counter):
        class Result:
            audio = np.array([0.0, 0.25, -0.25], dtype=np.float32)
            sample_rate = 16000
            markers = [{"name": "start", "char_offset": 2, "sample_offset": 16000}]
            trace = type("Trace", (), {"warnings": ["ssmd.warning: copied"]})()
            document_metadata = {
                "title": "Title",
                "voice_bindings": {"narrator": "af_bella"},
                "pause_defaults": {"sentence": "250ms"},
                "ignored": "not retained",
            }

            def release_audio(self):
                release_counter["count"] += 1

        return Result()

    def test_releases_after_successful_write_and_copies_data(self, tmp_path):
        release_counter = {"count": 0}
        converter = self._converter(tmp_path)
        result = self._result(release_counter)
        converter._runner = MagicMock()
        converter._runner.synthesize.return_value = result

        rendered = converter._render_chapter_wav(
            Chapter("Chapter", "text"),
            tmp_path / "chapter.wav",
            "text",
            tmp_path / "chapter.ssmd",
        )

        assert isinstance(rendered, RenderedChapter)
        assert release_counter["count"] == 1
        assert rendered.duration == pytest.approx(3 / 16000)
        assert rendered.sample_rate == 16000
        assert rendered.diagnostics[0].code == "ssmd.warning"
        assert rendered.markers[0]["time_s"] == 1.0
        assert rendered.document_metadata == {
            "title": "Title",
            "voice_bindings": {"narrator": "af_bella"},
            "pause_defaults": {"sentence": "250ms"},
        }
        samples, sample_rate = sf.read(rendered.rendered_path)
        assert sample_rate == 16000
        assert np.allclose(samples, result.audio)

    def test_releases_and_removes_temp_file_after_write_failure(
        self, tmp_path, monkeypatch
    ):
        release_counter = {"count": 0}
        converter = self._converter(tmp_path)
        converter._runner = MagicMock()
        converter._runner.synthesize.return_value = self._result(release_counter)

        class FailingSoundFile:
            def __init__(self, *_args, **_kwargs):
                raise OSError("cannot write wav")

        monkeypatch.setattr("ttsforge.conversion.sf.SoundFile", FailingSoundFile)

        with pytest.raises(OSError, match="cannot write wav"):
            converter._render_chapter_wav(
                Chapter("Chapter", "text"),
                tmp_path / "chapter.wav",
                "text",
                tmp_path / "chapter.ssmd",
            )

        assert release_counter["count"] == 1
        assert not list(tmp_path.glob(".chapter.wav.*.tmp.wav"))

    def test_previous_result_is_unreachable_before_next_synthesis(self, tmp_path):
        import gc
        import weakref

        release_counter = {"count": 0}
        first_ref = None

        class Runner:
            calls = 0

            def synthesize(self, *_args, **_kwargs):
                nonlocal first_ref
                self.calls += 1
                result = TestChapterRendering._result(release_counter)
                if self.calls == 1:
                    first_ref = weakref.ref(result)
                elif first_ref is not None:
                    gc.collect()
                    assert first_ref() is None
                return result

        converter = self._converter(tmp_path)
        converter._runner = Runner()
        for index in range(2):
            rendered = converter._render_chapter_wav(
                Chapter(f"Chapter {index}", "text"),
                tmp_path / f"chapter-{index}.wav",
                "text",
                tmp_path / f"chapter-{index}.ssmd",
            )
            rendered.rendered_path.unlink()

        assert release_counter["count"] == 2
