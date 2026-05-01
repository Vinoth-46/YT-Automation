import asyncio
import aiohttp
import os

async def test():
    headers = {
        'Authorization': f"Bearer {os.getenv('OPENROUTER_API_KEY')}", 
        'Content-Type': 'application/json'
    }
    models = [
        'meta-llama/llama-3-8b-instruct:free', 
        'google/gemma-2-9b-it:free', 
        'mistralai/mistral-7b-instruct:free',
        'qwen/qwen-2-7b-instruct:free'
    ]
    
    async with aiohttp.ClientSession() as s:
        for m in models:
            payload = {'model': m, 'messages': [{'role':'user','content':'hi'}]}
            async with s.post('https://openrouter.ai/api/v1/chat/completions', headers=headers, json=payload) as r:
                print(f"Model: {m}, Status: {r.status}")
                if r.status != 200:
                    print(await r.text())

asyncio.run(test())
