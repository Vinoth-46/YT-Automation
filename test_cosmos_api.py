import os
import shutil
import logging
from gradio_client import Client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_ai_video(prompt: str, output_file: str = "ai_sample.mp4"):
    """Generates an AI video clip from prompt using LTX-Video / Wan 2.1 AI models."""
    print("=" * 60)
    print("🎬 AI Text-to-Video Generation Test")
    print(f"Prompt: '{prompt}'")
    print("=" * 60)

    # Attempt 1: LTX-Video Distilled (Ultra-fast, ~15-20 sec)
    try:
        logger.info("Connecting to LTX-Video AI Model ('Lightricks/ltx-video-distilled')...")
        client = Client("Lightricks/ltx-video-distilled")
        
        result, seed = client.predict(
            prompt=prompt,
            negative_prompt="worst quality, inconsistent motion, blurry, jittery, distorted, lowres",
            input_image_filepath=None,
            input_video_filepath=None,
            height_ui=896,
            width_ui=512,
            mode="text-to-video",
            duration_ui=3,
            ui_frames_to_use=9,
            seed_ui=42,
            randomize_seed=True,
            ui_guidance_scale=1,
            improve_texture_flag=True,
            api_name="/text_to_video"
        )
        
        if result and isinstance(result, dict) and result.get("video"):
            video_temp = result.get("video")
            if os.path.exists(video_temp):
                shutil.copy(video_temp, output_file)
                abs_path = os.path.abspath(output_file)
                print(f"\n✅ SUCCESS! AI Video generated and saved to:")
                print(f"   {abs_path}")
                return abs_path
    except Exception as e:
        logger.warning(f"LTX-Video failed ({e}). Trying Wan 2.1 fallback...")

    # Attempt 2: Wan 2.1 (Fallback)
    try:
        logger.info("Connecting to Wan 2.1 AI Model ('Wan-AI/Wan2.1')...")
        client = Client("Wan-AI/Wan2.1")
        
        submission = client.predict(
            prompt=prompt,
            size="720*1280",
            watermark_wan=False,
            seed=-1,
            api_name="/t2v_generation_async"
        )
        
        import time
        for attempt in range(30):
            time.sleep(8)
            status = client.predict(api_name="/status_refresh")
            video_info = status[0] if status else None
            if video_info and isinstance(video_info, dict) and video_info.get("video"):
                video_temp = video_info["video"]
                if os.path.exists(video_temp):
                    shutil.copy(video_temp, output_file)
                    abs_path = os.path.abspath(output_file)
                    print(f"\n✅ SUCCESS! Wan 2.1 AI Video saved to:")
                    print(f"   {abs_path}")
                    return abs_path
    except Exception as e:
        logger.error(f"Wan 2.1 failed: {e}")

    print("\n❌ AI Video Generation failed.")
    return None

if __name__ == "__main__":
    prompt_text = "Cinematic tracking shot of a brick mason spreading mortar and laying red clay bricks, close-up, photorealistic, 4k"
    generate_ai_video(prompt_text)
