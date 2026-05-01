import asyncio
from engines.audio_engine import AudioEngine
import os

async def test():
    engine = AudioEngine()
    # Test script data
    script_data = {"narration": "வணக்கம், இது ஒரு சோதனை ஒலிப்பதிவு."}
    job_id = 999
    
    output = await engine.generate_narration(script_data, job_id)
    print(f"Generated output path: {output}")
    
    if output and os.path.exists(output):
        size = os.path.getsize(output)
        print(f"File exists. Size: {size} bytes")
    else:
        print("File does NOT exist.")

if __name__ == "__main__":
    asyncio.run(test())
