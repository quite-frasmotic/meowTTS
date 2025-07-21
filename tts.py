import asyncio
import re
import os

from elevenlabs.client import AsyncElevenLabs

API_KEY = os.environ.get("ELEVENLABS_API_KEY")
client = AsyncElevenLabs(api_key=API_KEY)

VOICE_IDS = {
    "stakie": "pW753uRkgLpjrcDGLbgl",
    "cowboy": "OYWwCdDHouzDwiZJWOOu",
    "funky": "5VUpBkCG0HfPjgfcv2wS",
}
DEFAULT_VOICE_ID = "OYWwCdDHouzDwiZJWOOu"


async def generate(user, message):
    match = re.match(r"^\[([^\]]+)\]\s*", message)
    voice_name = match[1].strip().lower() if match else None
    selected_voice = VOICE_IDS.get(voice_name or "", DEFAULT_VOICE_ID)
    clean_message = message[match.end() :] if match else message

    audio_stream = client.text_to_speech.stream(
        text=clean_message,
        voice_id=selected_voice,
        model_id="eleven_flash_v2_5",
        output_format="mp3_44100_128",
        # optimize_streaming_latency=4
    )

    return audio_stream


if __name__ == "__main__":
    asyncio.run(generate("bazinga", "Bingo bango bongo"))
