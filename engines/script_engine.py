import google.generativeai as genai
from core.config import settings
from core.database import get_scripts_collection
import logging
import json
import re

logger = logging.getLogger(__name__)

# Configure Gemini
genai.configure(api_key=settings.GEMINI_API_KEY)

class ScriptEngine:
    def __init__(self, model_name="gemini-1.5-flash"):
        self.model = genai.GenerativeModel(model_name)

    async def generate_topic(self, existing_topics=None):
        """Generate a fresh civil engineering topic in Tamil and English."""
        prompt = (
            "Generate a unique and highly engaging civil engineering topic for a 60-second YouTube Short. "
            "The topic should be educational, surprising, or solving a common construction problem. "
            "Provide the output in JSON format with 'title_en' and 'title_ta' keys. "
            f"Avoid these topics: {existing_topics or 'None'}"
        )
        
        response = self.model.generate_content(prompt)
        try:
            # Clean response text in case of markdown formatting
            text = re.search(r'\{.*\}', response.text, re.DOTALL).group()
            return json.loads(text)
        except Exception as e:
            logger.error(f"Failed to parse topic JSON: {e}")
            return {"title_en": "Modern Bridge Engineering", "title_ta": "நவீன பாலம் பொறியியல்"}

    async def generate_script(self, topic, retry_count=0):
        """Generate a full script in Tamil with hook, body, and CTA."""
        variation_instruction = ""
        if retry_count > 0:
            variation_instruction = "IMPORTANT: Use a completely different hook style and explanation pattern than usual to avoid repetition."

        prompt = (
            f"Write a 60-second YouTube Shorts script for the civil engineering topic: {topic['title_en']}. "
            "Language: Tamil. "
            f"{variation_instruction} "
            "Structure: "
            "1. Hook (3-5 seconds) - Grab attention. "
            "2. Educational Body (45-50 seconds) - Explain clearly with technical terms but simple Tamil. "
            "3. Call to Action (5-10 seconds). "
            "Also provide a 'narration' field which is the text to be spoken, and 'scenes' which is a list of visual descriptions for each part. "
            "Include 'metadata' with title, description, and tags. "
            "Format: JSON."
        )

        response = self.model.generate_content(prompt)
        try:
            text = re.search(r'\{.*\}', response.text, re.DOTALL).group()
            script_data = json.loads(text)
            
            # --- Monetization Safeguard: Similarity Check ---
            is_too_similar = await self.check_similarity(script_data.get("narration", ""))
            if is_too_similar and retry_count < 2:
                logger.warning("Generated script is too similar to past content. Regenerating with variation...")
                return await self.generate_script(topic, retry_count + 1)
            
            # Save to DB
            collection = get_scripts_collection()
            await collection.insert_one({
                "topic": topic,
                "script": script_data,
                "language": "ta",
                "narration_hash": hash(script_data.get("narration", ""))
            })
            
            return script_data
        except Exception as e:
            logger.error(f"Failed to parse script JSON: {e}")
            return None

    async def check_similarity(self, new_narration):
        """Check if the script is too similar to previous ones (Monetization safety)."""
        if not new_narration:
            return False
            
        collection = get_scripts_collection()
        # Fetch last 20 scripts
        cursor = collection.find().sort("_id", -1).limit(20)
        
        new_words = set(re.findall(r'\w+', new_narration.lower()))
        
        async for doc in cursor:
            old_narration = doc.get("script", {}).get("narration", "")
            if not old_narration:
                continue
                
            old_words = set(re.findall(r'\w+', old_narration.lower()))
            
            # Jaccard Similarity
            intersection = new_words.intersection(old_words)
            union = new_words.union(old_words)
            similarity = len(intersection) / len(union) if union else 0
            
            if similarity > 0.7: # 70% threshold
                return True
                
        return False
