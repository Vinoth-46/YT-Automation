import asyncio
import os
import sys
import logging
from google import genai
from core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_all_keys")

async def test_keys():
    api_keys = [k.strip() for k in settings.GEMINI_API_KEY.split(",") if k.strip()]
    print(f"Loaded {len(api_keys)} API keys.")
    
    models = [
        'gemini-2.5-flash',
        'gemini-2.0-flash',
        'gemini-1.5-flash',
        'gemini-2.0-flash-lite',
        'gemini-1.5-pro'
    ]
    
    for i, key in enumerate(api_keys):
        print(f"\n================ TESTING KEY #{i+1} ================")
        client = genai.Client(api_key=key, http_options={'api_version': 'v1beta'})
        
        for model in models:
            for use_search in [True, False]:
                search_str = "with search" if use_search else "without search"
                print(f"Testing model {model} {search_str}...")
                try:
                    tools = [{"google_search": {}}] if use_search else None
                    # Use a very short prompt to test connectivity
                    response = await asyncio.to_thread(
                        client.models.generate_content,
                        model=model,
                        contents="Say hello",
                        config={"tools": tools} if tools else None
                    )
                    print(f"  -> SUCCESS! Text: {response.text.strip()}")
                except Exception as e:
                    print(f"  -> FAILED: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(test_keys())
