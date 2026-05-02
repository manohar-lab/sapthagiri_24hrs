import edge_tts
import io

class Synthesizer:
    def __init__(self, voice="en-US-ChristopherNeural"):
        # Christopher or Aria are good English voices.
        # For Hinglish, "hi-IN-MadhurNeural" or "hi-IN-SwaraNeural" could be used.
        self.voice = voice

    async def synthesize(self, text: str) -> bytes:
        """
        Synthesizes text to speech using edge-tts.
        Returns MP3/WAV bytes.
        """
        communicate = edge_tts.Communicate(text, self.voice)
        audio_data = bytearray()
        
        # We can stream this to the client chunk by chunk in a real scenario,
        # but for simplicity we'll collect it all and send.
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data.extend(chunk["data"])
                
        return bytes(audio_data)
