import io
import wave
from faster_whisper import WhisperModel
import tempfile
import os

class Transcriber:
    def __init__(self, model_size="base"):
        # Use base or small for fast real-time CPU transcription. Use small or medium if GPU is available.
        # large-v3 is best for Hinglish but slower.
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
        
    async def transcribe(self, audio_bytes: bytes) -> str:
        """
        Transcribes audio bytes to text using faster-whisper.
        Assumes audio is 16kHz mono WAV.
        """
        # Save bytes to a temporary file since faster_whisper needs a file path or file-like object
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
            temp_audio.write(audio_bytes)
            temp_path = temp_audio.name
            
        try:
            segments, info = self.model.transcribe(temp_path, beam_size=5)
            text = "".join([segment.text for segment in segments])
            return text.strip()
        finally:
            os.remove(temp_path)
