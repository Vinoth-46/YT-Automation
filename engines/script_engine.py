import asyncio
from core.config import settings
from core.database import Database
from core.models import ScriptAsset
from sqlalchemy import select, desc
import logging
import json
import re
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

class ScriptEngine:
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_name = 'gemini-2.5-flash'

    async def _generate_content(self, prompt, max_retries=3):
        """Make an async request to Gemini API with retries and a fallback model."""
        # --- Cool-down Delay for Free Tier ---
        await asyncio.sleep(8)
        
        models_to_try = [self.model_name, 'gemini-3-flash-preview', 'gemini-2.0-flash']
        
        for model in models_to_try:
            for attempt in range(max_retries):
                try:
                    # We use asyncio.to_thread because the new google-genai client's async support
                    # is currently best invoked via thread pool for simple generate_content calls
                    # Wrap the thread in asyncio.wait_for so a silent SDK hang doesn't freeze the bot
                    response = await asyncio.wait_for(
                        asyncio.to_thread(
                            self.client.models.generate_content,
                            model=model,
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                temperature=0.9,
                            )
                        ),
                        timeout=60
                    )
                    logger.info(f"Gemini API success with model {model} on attempt {attempt+1}")
                    return response.text
                except asyncio.TimeoutError:
                    logger.warning(f"Job timed out generating script with {model} on attempt {attempt+1}. Retrying...")
                    continue
                except Exception as e:
                    error_str = str(e).lower()
                    if "429" in error_str or "quota" in error_str or "exhausted" in error_str:
                        logger.warning(f"Rate limit hit for {model}: {e}. Falling back to next model immediately.")
                        break # Skip remaining retries for this model and go to the next one
                        
                    wait_time = (2 ** attempt) * 2
                    logger.warning(f"Gemini API error with {model} (attempt {attempt+1}): {e}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)

        logger.error("All Gemini API models and retries failed.")
        return None

    async def generate_full_content(self, existing_topics=None):
        """Mega-Prompt: Generate Topic and Script with Kitchaa's Enterprises branding."""
        business_details = (
            "Name: Nirmal .B.E(Civil)\n"
            "Business: Kitchaa's Enterprises\n"
            "Phone: 8344051846\n"
            "Email: Kitchaasenterprise@gmail.com\n"
            "Website: https://kitchaa-enterprise.netlify.app/\n"
            "Instagram: https://www.instagram.com/nirmal.sunjaiy369?igsh=cmZzZnZ3MWt1eTA2\n"
            "Services: 1. Building Approvals, 2. Complete Construction & Consulting, "
            "3. Building Plans & Bank Estimates, 4. Bank Loan Assistance & Finance"
        )
        
        prompt = (
            f"You are an expert Civil Engineering content creator for YouTube Shorts. "
            "TASK: Generate a unique topic AND a full 60-second script in ONE go. "
            f"EXCLUDE these previous topics: {existing_topics or 'None'}. "
            "\n\nBRANDING REQUIREMENTS:\n"
            f"You MUST promote this business in the script and metadata:\n{business_details}\n\n"
            "1. TOPIC: A viral-style civil engineering mystery, hack, or fact.\n"
            "2. SCRIPT (TAMIL): Must have a Hook (5s), Body (50s), and a CTA (5s).\n"
            "   CRITICAL: The CTA must say exactly this: 'மேலும் பல சிவில் தகவல்களுக்கு Subscribe செய்யுங்கள்! உங்கள் கனவு இல்லத்திற்கு உடனே தொடர்பு கொள்ளுங்கள் - Kitchaa's Enterprises! முழு விவரங்கள் Description-ல் உள்ளது.'\n"
            "3. VISUALS: Provide a SIMPLE, 1-3 word English 'visual_query' for Pexels search (e.g. 'pouring concrete', 'crane', 'bricks'). DO NOT write full sentences.\n"
            "4. METADATA (SEO): The YouTube description MUST include the full Business Name, Contact Number, "
            "Email, Website link, Instagram link, and the 4 key services listed above to reach a wider audience.\n\n"
            "OUTPUT FORMAT (JSON ONLY):\n"
            "{\n"
            "  'topic': {'title_en': '...', 'title_ta': '...'},\n"
            "  'script': {\n"
            "    'narration': '...', \n"
            "    'scenes': [\n"
            "      {'visual_query': 'specific technical action'}\n"
            "    ],\n"
            "    'metadata': {'title': '...', 'description': '...', 'tags': [...]}\n"
            "  }\n"
            "}"
        )

        response_text = await self._generate_content(prompt)

        if not response_text:
            return None
            
        try:
            text = re.search(r'\{.*\}', response_text, re.DOTALL).group()
            data = json.loads(text)
            
            # Perform similarity check on the combined output
            similarity_score = await self.calculate_similarity(data['script'].get("narration", ""))
            data['script']["similarity_score"] = similarity_score
            
            if similarity_score > settings.SIMILARITY_THRESHOLD:
                logger.warning(f"Similarity {similarity_score} high. Retrying Mega-Prompt...")
                return await self.generate_full_content(existing_topics)
                
            return data
        except Exception as e:
            logger.error(f"Mega-Prompt parsing failed: {e}")
            return None


    async def generate_topic(self, existing_topics=None):
        """Generate a fresh civil engineering topic."""
        prompt = (
            "Generate a unique and highly engaging civil engineering topic for a 120-second YouTube Short. "
            "Focus on construction hacks, engineering marvels, or educational myths. "
            "Provide output in JSON ONLY: {'title_en': '...', 'title_ta': '...'}. "
            f"Avoid these existing topics: {existing_topics or 'None'}"
        )
        
        response_text = await self._generate_content(prompt)
        if not response_text:
            return {"title_en": "Concrete Durability Tips", "title_ta": "கான்கிரீட் ஆயுள் குறிப்புகள்"}
        try:
            text = re.search(r'\{.*\}', response_text, re.DOTALL).group()
            return json.loads(text)
        except Exception as e:
            logger.error(f"Failed to parse topic: {e}")
            return {"title_en": "Concrete Durability Tips", "title_ta": "கான்கிரீட் ஆயுள் குறிப்புகள்"}

    async def generate_script(self, topic, retry_count=0):
        """Generate a script with monetization safety (diversity)."""
        variation = ""
        if retry_count > 0:
            variation = "CRITICAL: Use a completely unique hook style (e.g., 'Did you know?', 'Stop doing this...', 'The secret of...') and a different explanation structure to ensure originality."

        prompt = (
            f"Write a 60-second YouTube Shorts script in Tamil for: {topic['title_en']}. "
            f"{variation} "
            "Requirements: "
            "1. Hook (5s) "
            "2. Body (50s) with technical civil engineering terms. "
            "3. CTA (5s). "
            "4. Exactly 6 scenes total. "
            "Provide ONLY valid JSON exactly matching this structure: "
            "{'narration': 'Full Tamil script here', "
            "'scenes': [{'visual_query': 'specific english search term for stock video'}], "
            "'metadata': {'title': '...', 'description': '...', 'tags': [...]}} "
            "Make sure 'visual_query' is a concise 2-3 word English keyword. "
            "IMPORTANT: Every query MUST contain a technical construction word (e.g. 'construction site', 'civil engineering', 'bridge work') "
            "to ensure Pexels doesn't return unrelated lifestyle footage (like people smoking or walking). "
            "Avoid general words like 'woman', 'man', 'city', 'street' alone."
        )

        response_text = await self._generate_content(prompt)
        if not response_text:
            return None
        try:
            text = re.search(r'\{.*\}', response_text, re.DOTALL).group()
            script_data = json.loads(text)
            
            # --- Monetization Safeguard: Similarity Check ---
            similarity_score = await self.calculate_similarity(script_data.get("narration", ""))
            if similarity_score > settings.SIMILARITY_THRESHOLD and retry_count < 2:
                logger.warning(f"Similarity score {similarity_score} exceeds threshold. Regenerating...")
                return await self.generate_script(topic, retry_count + 1)
            
            script_data["similarity_score"] = similarity_score
            return script_data
        except Exception as e:
            logger.error(f"Failed to parse script: {e}")
            return None

    async def calculate_similarity(self, new_text):
        """Check against last 50 scripts in PostgreSQL for repetition risk."""
        if not new_text: return 0.0
        
        async with Database.get_session() as session:
            result = await session.execute(
                select(ScriptAsset).order_by(desc(ScriptAsset.id)).limit(50)
            )
            past_scripts = result.scalars().all()
            
            if not past_scripts: return 0.0
            
            new_words = set(re.findall(r'\w+', new_text.lower()))
            max_similarity = 0.0
            
            for past in past_scripts:
                old_words = set(re.findall(r'\w+', past.script_text.lower()))
                intersection = new_words.intersection(old_words)
                union = new_words.union(old_words)
                sim = len(intersection) / len(union) if union else 0
                max_similarity = max(max_similarity, sim)
                
            return max_similarity
