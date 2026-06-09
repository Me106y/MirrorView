"""
TTS Client for MirrorView
==========================
HTTP client that fetches TTS audio from the MirrorView server's TTS endpoint.

Handles streaming PCM retrieval and feeds it to AudioPlayer for real-time playback.

Usage:
    from tts_integration.client.tts_client import TTSClient
    from tts_integration.client.audio_player import AudioPlayer

    client = TTSClient(base_url="http://localhost:5001")
    player = AudioPlayer()

    # Stream and play TTS audio
    player.start()
    for chunk in client.stream_tts("Hello, welcome!", mode="sentence"):
        player.feed(chunk)
    player.finish()
    player.wait()
"""

import logging
from typing import Generator, Optional

import requests

logger = logging.getLogger(__name__)


class TTSClient:
    """
    HTTP client for the MirrorView TTS API endpoint.

    Args:
        base_url: Server base URL (default: http://localhost:5001)
        api_key: API key for Boson.ai (if not set server-side)
        timeout: Request timeout in seconds
    """

    def __init__(
        self,
        base_url: str = "http://localhost:5001",
        api_key: Optional[str] = None,
        timeout: int = 180,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def stream_tts(
        self,
        text: str,
        voice: str = "default",
        mode: str = "full",
        interview_id: Optional[int] = None,
    ) -> Generator[bytes, None, None]:
        """
        Stream TTS audio from the server.

        Args:
            text: Text to synthesize
            voice: Voice preset name
            mode: "full" (entire text at once) or "sentence" (per-sentence)
            interview_id: Optional interview context

        Yields:
            Raw PCM audio chunks
        """
        url = f"{self.base_url}/api/tts/synthesize"
        payload = {
            "text": text,
            "voice": voice,
            "mode": mode,
        }
        if interview_id:
            payload["interview_id"] = interview_id

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        with requests.post(
            url,
            json=payload,
            headers=headers,
            stream=True,
            timeout=self.timeout,
        ) as r:
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=4096):
                if chunk:
                    yield chunk

    def speak_and_play(
        self,
        text: str,
        voice: str = "default",
        mode: str = "sentence",
        volume: float = 1.0,
        interview_id: Optional[int] = None,
    ):
        """
        Convenience method: stream TTS and play it synchronously.

        This is a blocking call — use in a background thread for GUI apps.

        Args:
            text: Text to speak
            voice: Voice preset
            mode: Streaming mode ("full" or "sentence")
            volume: Playback volume
            interview_id: Optional interview context

        Returns:
            AudioPlayer instance (can check .progress, .error, etc.)
        """
        from tts_integration.client.audio_player import AudioPlayer

        player = AudioPlayer(volume=volume)
        player.start()

        for chunk in self.stream_tts(
            text=text,
            voice=voice,
            mode=mode,
            interview_id=interview_id,
        ):
            player.feed(chunk)

        player.finish()
        player.wait()
        return player
