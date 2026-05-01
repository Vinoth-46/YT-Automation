import os
from google import genai
from core.config import settings

def test():
    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents='Generate a test JSON: {"test": "ok"}'
        )
        print("Success:", response.text)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test()
