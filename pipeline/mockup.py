"""
Integrates with local ComfyUI API to generate an SD 1.5 architectural mockup.
"""
import httpx
import time
import os
import uuid
from config import COMFYUI_API_URL, SD_CHECKPOINT

def generate_mockup(analysis: dict) -> dict:
    """Generate architecture mockup using ComfyUI REST API."""
    dev_type = analysis.get("recommended_development", "apartments")
    
    prompts = {
        "apartments": "modern minimal apartment building exterior, concrete and glass, daytime, real photo, architectural photography, hyperrealistic, 8k",
        "villas": "luxury modern villa exterior, parametric design, pool, daytime, real photo, architectural photography, hyperrealistic",
        "commercial": "modern commercial plaza building exterior, glass facade, retail stores, architectural photography",
        "mixed": "modern mixed use tower exterior, residential and retail, daytime, real photo, architectural photography"
    }
    
    positive_prompt = prompts.get(dev_type.lower(), prompts["apartments"])
    
    workflow = {
        "4": {"class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": SD_CHECKPOINT}},
        "6": {"class_type": "CLIPTextEncode",
            "inputs": {"text": positive_prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode",
            "inputs": {"text": "ugly, blurry, low quality", "clip": ["4", 1]}},
        "3": {"class_type": "KSampler",
            "inputs": {"seed": int(time.time()), "steps": 20, "cfg": 7,
                    "sampler_name": "euler", "scheduler": "normal",
                    "denoise": 1.0, "model": ["4", 0],
                    "positive": ["6", 0], "negative": ["7", 0],
                    "latent_image": ["5", 0]}},
        "5": {"class_type": "EmptyLatentImage",
            "inputs": {"width": 512, "height": 512, "batch_size": 1}},
        "8": {"class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage",
            "inputs": {"filename_prefix": f"land_mockup_{uuid.uuid4().hex[:6]}", "images": ["8", 0]}}
    }
    
    try:
        r = httpx.post(f"{COMFYUI_API_URL}/prompt", json={"prompt": workflow}, timeout=5)
        prompt_id = r.json()["prompt_id"]
        
        start = time.time()
        while time.time() - start < 120:
            history = httpx.get(f"{COMFYUI_API_URL}/history/{prompt_id}").json()
            if prompt_id in history:
                filename = history[prompt_id]["outputs"]["9"]["images"][0]["filename"]
                img_data = httpx.get(f"{COMFYUI_API_URL}/view?filename={filename}").content
                
                output_path = f"output/mockups/{filename}"
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(img_data)
                
                return {"image_path": output_path}
            time.sleep(2)
            
        raise TimeoutError("ComfyUI generation timeout")
        
    except Exception as e:
        print(f"[mockup] Generation failed: {e}")
        return {}
