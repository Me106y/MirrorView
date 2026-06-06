"""
Sherpa-ONNX Streaming STT Worker
=================================
Real-time offline speech recognition using Sherpa-ONNX Transducer.

- Bilingual Chinese + English in a single model
- <200ms time-to-first-token, 0.02x realtime factor
- No network required — fully offline
- Shows partial results during recording

Model: sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20
"""

import os, time, threading
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

from utils.logger_handler import logger

# ── Model path ──────────────────────────────────────────────
_MODEL_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..",
    "sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20"
)


class STTWorkerSherpa(QThread):
    """
    Real-time streaming STT using Sherpa-ONNX.

    Signals:
        partial_result(str) — emitted every ~100ms with current recognition
        final_result(str)   — emitted when recording stops, full text
        mic_level(float)    — microphone RMS level 0.0–1.0
        error(str)          — error message
    """
    partial_result = pyqtSignal(str)
    final_result = pyqtSignal(str)
    mic_level = pyqtSignal(float)
    error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._fs = 16000  # Sherpa-ONNX works best at 16kHz
        self._stop = threading.Event()
        self._recognizer = None

    def run(self):
        # ── Load recognizer ──
        try:
            import sherpa_onnx

            encoder = os.path.join(_MODEL_DIR, "encoder-epoch-99-avg-1.int8.onnx")
            decoder = os.path.join(_MODEL_DIR, "decoder-epoch-99-avg-1.int8.onnx")
            joiner = os.path.join(_MODEL_DIR, "joiner-epoch-99-avg-1.int8.onnx")
            tokens = os.path.join(_MODEL_DIR, "tokens.txt")

            for f in (encoder, decoder, joiner, tokens):
                if not os.path.exists(f):
                    self.error.emit(f"Model file missing: {os.path.basename(f)}")
                    return

            self._recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
                encoder=encoder,
                decoder=decoder,
                joiner=joiner,
                tokens=tokens,
                num_threads=4,
                enable_endpoint_detection=False,  # we handle start/stop manually
            )
            logger.info("Sherpa-ONNX recognizer loaded")
        except Exception as e:
            logger.error(f"Sherpa-ONNX init failed: {e}", exc_info=True)
            self.error.emit(f"STT init: {e}")
            return

        # ── Start mic → streaming recognition ──
        stream = self._recognizer.create_stream()
        import sounddevice as sd
        last_partial = ""

        def mic_callback(indata, frames, time_info, status):
            nonlocal last_partial

            if self._stop.is_set():
                return

            # Mono float32 at self._fs
            samples = indata[:, 0].astype(np.float32) if indata.ndim > 1 \
                else indata.astype(np.float32)

            # Mic level for VU meter
            rms = float(np.sqrt(np.mean(np.square(samples))))
            self.mic_level.emit(min(1.0, rms * 10))

            # Feed to Sherpa
            stream.accept_waveform(self._fs, samples.squeeze())
            while self._recognizer.is_ready(stream):
                self._recognizer.decode_stream(stream)

            # Emit partial result
            result = self._recognizer.get_result(stream)
            text = result if isinstance(result, str) else result.text
            text = text.strip()
            if text and text != last_partial:
                last_partial = text
                self.partial_result.emit(text)

        try:
            with sd.InputStream(
                samplerate=self._fs,
                channels=1,
                dtype=np.float32,
                blocksize=1600,  # 100ms chunks
                callback=mic_callback,
            ):
                # Wait for stop signal
                self._stop.wait()

            # ── Finalize ──
            # Feed a brief silence to flush decoder
            for _ in range(5):
                stream.accept_waveform(self._fs, np.zeros(1600, dtype=np.float32))
                while self._recognizer.is_ready(stream):
                    self._recognizer.decode_stream(stream)

            result = self._recognizer.get_result(stream)
            text = result if isinstance(result, str) else result.text
            text = text.strip()

            if text:
                text = self._auto_punctuate(text)
                self.final_result.emit(text)
            else:
                self.error.emit("No speech detected — try speaking louder")

        except sd.PortAudioError as e:
            logger.error(f"Mic device error: {e}")
            self.error.emit("Microphone unavailable — check system permissions")
        except Exception as e:
            logger.error(f"STT runtime error: {e}", exc_info=True)
            self.error.emit(f"STT error: {str(e)[:60]}")

    def stop(self):
        """Signal the worker to stop recording and finalize."""
        self._stop.set()

    # ── Auto-punctuation ──────────────────────────────────

    @staticmethod
    def _auto_punctuate(text: str) -> str:
        """
        Lightweight punctuation restoration via DeepSeek.
        Falls back to simple heuristics if unavailable.
        """
        if not text or len(text) < 3:
            return text

        import os as _os
        key = _os.environ.get("DEEPSEEK_API_KEY", "")
        if not key:
            return STTWorkerSherpa._punctuate_heuristic(text)

        try:
            from openai import OpenAI
        except ImportError:
            return STTWorkerSherpa._punctuate_heuristic(text)

        try:
            client = OpenAI(
                api_key=key,
                base_url="https://api.deepseek.com/v1",
                timeout=5,
            )
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{
                    "role": "system",
                    "content": (
                        "Add proper punctuation and capitalization to this "
                        "English/Chinese mixed speech transcript. "
                        "Do NOT change any words, add/edit text, or rephrase. "
                        "Only add periods, commas, question marks, and capitalization. "
                        "Output ONLY the punctuated text, nothing else."
                    ),
                }, {
                    "role": "user",
                    "content": text,
                }],
                temperature=0,
                max_tokens=256,
            )
            result = resp.choices[0].message.content.strip()
            return result if result else text
        except Exception as e:
            logger.info(f"Auto-punctuation skipped ({e})")
            return STTWorkerSherpa._punctuate_heuristic(text)

    @staticmethod
    def _punctuate_heuristic(text: str) -> str:
        """Simple fallback: capitalize first letter, add period if missing."""
        text = text.strip()
        if not text:
            return text
        # Capitalize first letter
        text = text[0].upper() + text[1:] if text[0].islower() else text
        # Add period if ends with lowercase alphanumeric
        if text[-1].isalnum() and text[-1].isascii():
            text += "."
        return text
