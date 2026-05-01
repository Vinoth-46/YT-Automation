import asyncio
import os
from engines.video_engine import VideoEngine

async def test():
    engine = VideoEngine()
    
    # We will simulate scene paths using the existing ones from Job 19 if they exist.
    job_id = 999
    scene_paths = []
    
    # Find existing temp videos to simulate scenes
    temp_dir = "/app/temp"
    if os.path.exists(temp_dir):
        files = os.listdir(temp_dir)
        mp4_files = [os.path.join(temp_dir, f) for f in files if f.endswith('.mp4')]
        scene_paths = mp4_files[:3] # use up to 3 videos
        
    if not scene_paths:
        print("No temp videos found to test with.")
        return
        
    print(f"Using scenes: {scene_paths}")
    
    audio_path = "/app/outputs/999_narration.wav"
    if not os.path.exists(audio_path):
        # Fallback to an existing audio if available
        files = os.listdir("/app/outputs")
        wav_files = [os.path.join("/app/outputs", f) for f in files if f.endswith('.wav')]
        if wav_files:
            audio_path = wav_files[0]
        else:
            print("No audio found.")
            return
            
    print(f"Using audio: {audio_path}")
    
    output_path = f"/app/outputs/{job_id}_test_video.mp4"
    if os.path.exists(output_path):
        os.remove(output_path)
        
    success = await engine._render_ffmpeg(scene_paths, audio_path, output_path)
    
    if success:
        print("Video rendering succeeded!")
    else:
        print("Video rendering failed.")

if __name__ == "__main__":
    asyncio.run(test())
