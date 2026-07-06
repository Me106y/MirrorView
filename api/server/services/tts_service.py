"""
Higgs Audio v3 TTS Service
===========================
Wrapper around the Boson.ai Higgs Audio v3 Text-to-Speech API.

API Reference: https://docs.boson.ai/models/higgs-audio-tts/overview

Features:
- Streaming PCM audio synthesis (16-bit, 24kHz, mono)
- Voice presets (default, jake, etc.)
- Voice cloning via reference audio
- Inline emotion/style/prosody control tags
- Automatic sentence splitting for low-latency streaming
- Retry with exponential backoff

Usage:
    tts = HiggsAudioTTS(voice="default")

    # Stream PCM audio
    for chunk in tts.synthesize_stream("Hello, welcome to the interview!"):
        play(chunk)

    # Or synthesize full audio at once
    pcm_data = tts.synthesize("Hello, welcome to the interview!")
"""

import os
import re
import time
import logging
from typing import Generator, Optional, List

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://api.boson.ai/v1"
DEFAULT_MODEL = "higgs-audio-v3-tts"
DEFAULT_VOICE = "default"
DEFAULT_RESPONSE_FORMAT = "pcm"  # 16-bit, 24kHz, mono PCM
SAMPLE_RATE = 24000
SAMPLE_WIDTH = 2  # bytes per sample (16-bit)
NUM_CHANNELS = 1

# Max text length per TTS request (model-dependent; stay conservative)
MAX_CHUNK_LENGTH = 500

# Sentence boundary patterns for smart text splitting
SENTENCE_END_PATTERN = re.compile(
    r'(?<=[。！？.!?\n])\s*'
)

# ---------------------------------------------------------------------------
# Exception classes
# ---------------------------------------------------------------------------


class HiggsAudioError(Exception):
    """Base exception for Higgs Audio TTS errors."""


class HiggsAudioAuthError(HiggsAudioError):
    """Authentication failure — invalid or missing API key."""


class HiggsAudioRateLimitError(HiggsAudioError):
    """Rate limit exceeded."""


class HiggsAudioTimeoutError(HiggsAudioError):
    """Request timed out."""


# ---------------------------------------------------------------------------
# Main service class
# ---------------------------------------------------------------------------


class HiggsAudioTTS:
    """
    Boson.ai Higgs Audio v3 TTS service.

    Args:
        model: Model ID (default: "higgs-audio-v3-tts")
        voice: Preset voice identifier (default: "default")
        api_key: API key override (default: reads BOSON_API_KEY from env)
        base_url: API base URL override
        timeout: Request timeout in seconds
        max_retries: Max retry count for transient errors
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        voice: str = DEFAULT_VOICE,
        api_key: Optional[str] = None,
        base_url: str = BASE_URL,
        timeout: int = 180,
        max_retries: int = 3,
    ):
        self.model = model
        self.voice = voice
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

        # API key: parameter > env var
        self.api_key = api_key or os.environ.get("BOSON_API_KEY")
        if not self.api_key:
            logger.warning(
                "BOSON_API_KEY not set — TTS requests will fail. "
                "Set it via environment variable or pass api_key parameter."
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
    ) -> bytes:
        """
        Synthesize text to PCM audio (non-streaming).

        Args:
            text: Text to synthesize (supports inline control tags)
            voice: Override default voice
            ref_audio: Reference audio URL/base64 for voice cloning
            ref_text: Transcript of reference audio

        Returns:
            Raw PCM audio bytes (16-bit, 24kHz, mono, little-endian)

        Raises:
            HiggsAudioAuthError: API key invalid/missing
            HiggsAudioRateLimitError: Rate limited
            HiggsAudioError: Other API errors
        """
        payload = self._build_payload(
            text=text,
            voice=voice,
            ref_audio=ref_audio,
            ref_text=ref_text,
            stream=False,
            response_format="pcm",
        )

        pcm_data = bytearray()
        for attempt in range(1, self.max_retries + 1):
            try:
                with requests.post(
                    f"{self.base_url}/audio/speech",
                    headers=self._headers(),
                    json=payload,
                    stream=True,  # still use stream to read chunks
                    timeout=self.timeout,
                ) as r:
                    self._check_response(r)
                    # Non-streaming still returns chunks via iter_content
                    for chunk in r.iter_content(chunk_size=4096):
                        if chunk:
                            pcm_data.extend(chunk)
                return bytes(pcm_data)

            except requests.exceptions.Timeout:
                logger.warning(
                    f"TTS request timed out (attempt {attempt}/{self.max_retries})"
                )
                if attempt == self.max_retries:
                    raise HiggsAudioTimeoutError(
                        f"TTS synthesis timed out after {self.max_retries} attempts"
                    )
                time.sleep(2 ** attempt)

            except (HiggsAudioAuthError, HiggsAudioRateLimitError):
                raise  # don't retry auth/rate-limit errors

            except requests.exceptions.RequestException as e:
                logger.warning(
                    f"TTS request failed (attempt {attempt}/{self.max_retries}): {e}"
                )
                if attempt == self.max_retries:
                    raise HiggsAudioError(f"TTS synthesis failed: {e}") from e
                time.sleep(2 ** attempt)

    def synthesize_stream(
        self,
        text: str,
        voice: Optional[str] = None,
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
    ) -> Generator[bytes, None, None]:
        """
        Stream PCM audio chunks as they are generated.

        Yields raw PCM byte chunks (16-bit, 24kHz, mono).
        The first non-empty chunk indicates time-to-first-audio.

        Args:
            text: Text to synthesize
            voice: Override default voice
            ref_audio: Reference audio for voice cloning
            ref_text: Transcript of reference audio

        Yields:
            Raw PCM byte chunks

        Raises:
            Same as synthesize()
        """
        payload = self._build_payload(
            text=text,
            voice=voice,
            ref_audio=ref_audio,
            ref_text=ref_text,
            stream=True,
            response_format="pcm",
        )

        with requests.post(
            f"{self.base_url}/audio/speech",
            headers=self._headers(),
            json=payload,
            stream=True,
            timeout=self.timeout,
        ) as r:
            self._check_response(r)
            for chunk in r.iter_content(chunk_size=4096):
                if chunk:
                    yield chunk

    def synthesize_stream_sentences(
        self,
        text: str,
        voice: Optional[str] = None,
    ) -> Generator[bytes, None, None]:
        """
        Sentence-level streaming for low-latency conversational TTS.

        Splits input text at sentence boundaries and streams each
        sentence's audio as it becomes available. This allows playback
        to begin before the entire text is synthesized.

        Args:
            text: Full text to synthesize
            voice: Override default voice

        Yields:
            Raw PCM byte chunks (individual sentences may be yielded
            as they complete — downstream should handle concatenation)
        """
        sentences = self._split_sentences(text)
        logger.debug(f"Split text into {len(sentences)} sentence(s)")

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            yield from self.synthesize_stream(
                text=sentence,
                voice=voice,
            )

    def synthesize_chunks(
        self,
        chunks: List[str],
        voice: Optional[str] = None,
    ) -> Generator[bytes, None, None]:
        """
        Synthesize a list of pre-split text chunks in order.

        Useful when the caller already has sentence-level splits
        (e.g., from streaming LLM output).

        Args:
            chunks: List of text chunks
            voice: Override default voice

        Yields:
            Raw PCM byte chunks
        """
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            yield from self.synthesize_stream(
                text=chunk,
                voice=voice,
            )

    # ------------------------------------------------------------------
    # Control tag helpers
    # ------------------------------------------------------------------

    @staticmethod
    def emotion(text: str, emotion: str) -> str:
        """Wrap text with an emotion control tag."""
        return f"<|emotion:{emotion}|>{text}"

    @staticmethod
    def pause() -> str:
        """Insert a prosodic pause."""
        return "<|prosody:pause|>"

    @staticmethod
    def style(text: str, style: str) -> str:
        """Wrap text with a speaking style tag."""
        return f"<|style:{style}|>{text}"

    @staticmethod
    def sfx(text: str, effect: str) -> str:
        """Add a sound effect tag."""
        return f"<|sfx:{effect}|>{text}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict:
        """Build request headers."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(
        self,
        text: str,
        voice: Optional[str] = None,
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
        stream: bool = True,
        response_format: str = "pcm",
    ) -> dict:
        """Build the JSON request payload."""
        payload = {
            "model": self.model,
            "input": text,
            "voice": voice or self.voice,
            "response_format": response_format,
            "stream": stream,
        }

        if ref_audio:
            payload["ref_audio"] = ref_audio
        if ref_text:
            payload["ref_text"] = ref_text

        return payload

    def _check_response(self, response: requests.Response) -> None:
        """Check HTTP response and raise appropriate exceptions."""
        if response.status_code == 200:
            return

        error_body = ""
        try:
            error_body = response.text[:500]
        except Exception:
            pass

        if response.status_code == 401 or response.status_code == 403:
            raise HiggsAudioAuthError(
                f"Authentication failed (HTTP {response.status_code}). "
                "Check your BOSON_API_KEY."
            )
        elif response.status_code == 429:
            raise HiggsAudioRateLimitError(
                "Rate limit exceeded. Retry after: "
                f"{response.headers.get('Retry-After', 'unknown')}s"
            )
        else:
            raise HiggsAudioError(
                f"TTS API error (HTTP {response.status_code}): {error_body}"
            )

    @staticmethod
    def _split_sentences(text: str) -> List[str]:
        """Split text at sentence boundaries."""
        # Split at sentence-ending punctuation, keeping delimiters
        parts = SENTENCE_END_PATTERN.split(text)
        # Rejoin delimiter with preceding text
        sentences = []
        i = 0
        while i < len(parts):
            sentence = parts[i]
            if i + 1 < len(parts) and parts[i + 1] == "":
                # The delimiter was consumed; join with next part
                sentence += parts[i + 1] if i + 2 < len(parts) else ""
                i += 2
            else:
                i += 1
            if sentence.strip():
                sentences.append(sentence)
        return sentences if sentences else [text]


# ---------------------------------------------------------------------------
# Pre-configured voice presets (reference)
# ---------------------------------------------------------------------------

# Known preset voices for Higgs Audio v3.
# List may expand — check https://docs.boson.ai/models/higgs-audio-tts/voices
PRESET_VOICES = [
    "default",
    "jake",
    "emma",
    "sophia",
    "liam",
    "olivia",
    "noah",
    "ava",
    "ethan",
    "mia",
]
