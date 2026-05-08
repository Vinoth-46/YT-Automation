import os
from google import genai
from core.config import settings

def test():
    try:
        api_keys = [k.strip() for k in settings.GEMINI_API_KEY.split(",") if k.strip()]
        print(f"Found {len(api_keys)} keys.")
        
        for i, key in enumerate(api_keys):
            try:
                print(f"Testing Key #{i+1}...")
                client = genai.Client(api_key=key, http_options={'api_version': 'v1beta'})
                response = client.models.generate_content(
                    model='gemini-flash-latest',
                    contents='Generate a test JSON: {"test": "ok"}'
                )
                print(f"Success with Key #{i+1}:", response.text)
                return
            except Exception as e:
                print(f"Error with Key #{i+1}:", e)
    except Exception as e:
        print("General Error:", e)

if __name__ == "__main__":
    test()
