import os
import sys
import torch

# Print instructions for the user
print("=" * 60)
print("Wan 2.1 Text-to-Video Generator Test Script")
print("=" * 60)
print("Prerequisites:")
print("Make sure you have installed the required libraries:")
print("  pip install torch diffusers transformers accelerate")
print("=" * 60)

# Check for CUDA availability
if not torch.cuda.is_available():
    print("WARNING: CUDA is not available. Running this model on CPU will be extremely slow or run out of memory.")
    print("Please run this script on an environment with a GPU (e.g., Kaggle, Colab, or local GPU).")
    # We won't exit, but we warn the user.
else:
    print(f"CUDA is available! Using GPU: {torch.cuda.get_device_name(0)}")

try:
    from diffusers import WanPipeline, UniPCMultistepScheduler
    from diffusers.utils import export_to_video
except ImportError:
    print("\nError: Could not import 'diffusers' or other key libraries.")
    print("Please install them using:")
    print("  pip install diffusers transformers accelerate torch")
    sys.exit(1)

def run_test():
    # 1. Define Model ID
    # Using the 1.3B model which fits on consumer GPUs & Kaggle T4 GPUs
    model_id = "Wan-AI/Wan2.1-T2V-1.3B-Diffusers"
    output_filename = "wan_test_zoom_output.mp4"
    
    print(f"\n[1/4] Loading model: {model_id}...")
    
    # 2. Setup the flow scheduler (recommended configuration for Wan)
    scheduler = UniPCMultistepScheduler(
        prediction_type='flow_prediction',
        use_flow_sigmas=True,
        num_train_timesteps=1000,
        flow_shift=3.0  # 3.0 is optimal for 480p resolution
    )
    
    # 3. Load pipeline in bfloat16 for speed and memory efficiency
    pipe = WanPipeline.from_pretrained(
        model_id, 
        torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32
    )
    pipe.scheduler = scheduler
    
    if torch.cuda.is_available():
        # Enable memory optimizations to fit within Kaggle T4's 15GB VRAM
        pipe.enable_model_cpu_offload()
        pipe.vae.enable_slicing()
        pipe.vae.enable_tiling()
        
    print("[2/4] Model loaded successfully with memory optimizations.")

    # 4. Prompt specifically engineered for camera zoom (house to sunshade)
    prompt = "Camera slowly dollys in from a wide view of a modern luxury house, zooming in to focus closely on a sleek fabric sunshade on the patio, cinematic lighting, photorealistic, 4k."
    negative_prompt = "Bright tones, overexposed, static, blurred details, subtitles, style, worst quality, low quality"

    print(f"\n[3/4] Generating video...")
    print(f"Prompt: '{prompt}'")
    
    # Run the model
    # Height and Width are set to square dimensions and lower frame count to fit T4 VRAM
    with torch.inference_mode():
        output = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            height=480,
            width=480,
            num_frames=33,       # 33 frames is ~2 seconds (fits on Kaggle T4 VRAM)
            guidance_scale=5.0,  # Prompt guidance
            num_inference_steps=50
        ).frames[0]

    # 5. Save the output
    print(f"\n[4/4] Saving output video to {output_filename}...")
    export_to_video(output, output_filename, fps=16)
    
    print("\nSuccess! Video generated and saved.")
    print(f"File location: {os.path.abspath(output_filename)}")

if __name__ == "__main__":
    run_test()
