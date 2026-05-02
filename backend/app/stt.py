import io
import asyncio
import wave
from faster_whisper import WhisperModel
import tempfile
import os
import logging

logger = logging.getLogger(__name__)

class Transcriber:
    def __init__(self, model_size="base"):
        # Use base or small for fast real-time CPU transcription. Use small or medium if GPU is available.
        # large-v3 is best for Hinglish but slower.
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
        
    async def transcribe(self, audio_bytes: bytes) -> str:
        """
        Transcribes audio bytes to text using faster-whisper.
        Accepts browser-recorded audio (typically webm/opus) and wav.
        """
        # MediaRecorder usually sends webm/opus; choose suffix by header for decoder compatibility.
        suffix = ".wav" if audio_bytes[:4] == b"RIFF" else ".webm"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_audio:
            temp_audio.write(audio_bytes)
            temp_path = temp_audio.name
            
        try:
            def _run_sync():
                segments, info = self.model.transcribe(temp_path, beam_size=5)
                return "".join([segment.text for segment in segments])
            
            text = await asyncio.to_thread(_run_sync)
            text = text.strip()
            logger.info(f"[STT] Transcribed: '{text}'")
            return text
        except Exception as e:
            logger.error(f"STT transcription failed: {e}")
            return ""
        finally:
            os.remove(temp_path)
