import requests
import json
import base64

def get_base64(filepath):
    with open(filepath, "rb") as f:
        return f"data:audio/mp3;base64,{base64.b64encode(f.read()).decode()}"

def get_base64_img(filepath):
    with open(filepath, "rb") as f:
        return f"data:image/png;base64,{base64.b64encode(f.read()).decode()}"

audio_b64 = get_base64("output/day_01/audio.mp3")
img_b64 = get_base64_img("assets/avatar.png")

url = "https://kevinwang676-sadtalker.hf.space/run/predict"
payload = {
    "data": [
        img_b64,
        audio_b64,
        "crop",
        False,
        True,
        2,
        "512",
        0
    ]
}
headers = {"Content-Type": "application/json"}
try:
    response = requests.post(url, json=payload, headers=headers)
    print(response.status_code)
    print(response.text[:200])
except Exception as e:
    print(e)
