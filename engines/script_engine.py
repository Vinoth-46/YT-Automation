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
        # Support multiple keys separated by comma
        self.api_keys = [k.strip() for k in settings.GEMINI_API_KEY.split(",") if k.strip()]
        self.current_key_index = 0
        self.client = genai.Client(
            api_key=self.api_keys[0],
            http_options={'api_version': 'v1beta'}
        )
        # Setting default model to a stable text version
        self.model_name = 'gemini-1.5-flash'
        logger.info(f"Initialized ScriptEngine with {len(self.api_keys)} keys. Primary model: {self.model_name} (API v1beta)")

    def _rotate_key(self):
        """Switch to the next available API key."""
        if len(self.api_keys) > 1:
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            new_key = self.api_keys[self.current_key_index]
            self.client = genai.Client(
                api_key=new_key,
                http_options={'api_version': 'v1beta'}
            )
            logger.info(f"🔄 Rotated to Gemini API Key #{self.current_key_index + 1}")
            return True
        return False

    async def _generate_content(self, prompt, max_retries=3):
        """Make an async request to Gemini API with retries, key rotation, and fallbacks."""
        # Using the experimental models from your specific quota list
        models_to_try = [
            'models/gemini-flash-latest',   
            'models/gemini-1.5-flash',      
            'models/gemini-2.5-flash',      
            'models/gemini-2.0-flash',      
            'models/gemini-1.5-pro',        
            'models/gemini-pro-latest'      
        ]
        
        for model in models_to_try:
            for attempt in range(max_retries):
                try:
                    response = await asyncio.wait_for(
                        asyncio.to_thread(
                            self.client.models.generate_content,
                            model=model,
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                temperature=0.9,
                                tools=[types.Tool(google_search=types.GoogleSearch())]
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
                    
                    # Key Rotation logic for Rate Limits (429)
                    if "429" in error_str or "quota" in error_str or "exhausted" in error_str:
                        logger.warning(f"Rate limit hit for {model} with current key.")
                        if self._rotate_key():
                            # Retry immediately with the new key for the SAME model
                            continue 
                        else:
                            logger.warning(f"No more keys to rotate. Falling back to next model.")
                            break 
                    
                    # Longer wait for 503/Server Busy
                    wait_time = (2 ** attempt) * 5 # 5s, 10s, 20s
                    logger.warning(f"Gemini API busy or error with {model}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)

        logger.error("All Gemini API models and keys failed.")
        return None

    async def generate_full_content(self, existing_topics=None, custom_topic=None):
        """Mega-Prompt: Generate Topic and Script with Kitchaa's Enterprises branding."""
        business_details = (
            "Name: Nirmal .B.E(Civil)\n"
            "Business: Kitchaa's Enterprises\n"
            "Phone: 8344051846\n"
            "Email: Kitchaasenterprise@gmail.com\n"
            "Website: https://kitchaas-enterprise.com/\n"
            "Instagram: https://www.instagram.com/nirmal.sunjaiy369?igsh=cmZzZnZ3MWt1eTA2\n"
            "Services: 1. Building Approvals, 2. Complete Construction & Consulting, "
            "3. Building Plans & Bank Estimates, 4. Bank Loan Assistance & Finance"
        )
        
        # Format history for prompt
        history_text = "\n".join([f"- {t}" for t in (existing_topics or [])])
        
        topic_instruction = (
            f"Choose a FRESH, NEW engineering insight NOT in the blacklist above."
            if not custom_topic else
            f"Focus on this specific user-requested topic/instruction: '{custom_topic}'. Keep the civil engineering/house construction/home building theme."
        )
        
        prompt = (
            f"Role: Expert Civil Engineering Content Creator for YouTube Shorts.\n"
            f"Goal: Generate a unique topic AND a full 60-second script.\n\n"
            f"🔴 PREVIOUS TOPICS BLACKLIST (DO NOT REPEAT OR MIMIC THESE):\n"
            f"{history_text or 'None'}\n\n"
            f"BRANDING REQUIREMENTS (Kitchaa's Enterprises):\n"
            f"{business_details}\n\n"
            f"INSTRUCTIONS:\n"
            f"1. TOPIC: {topic_instruction}\n"
            f"2. TITLE: Generate a highly intriguing, clear, benefit-driven YouTube title (e.g. 'Why Your Bathroom Floor Is Lower (Must-Know Tip Before Tiling)' or 'Avoid This Huge Foundation Mistake!') instead of only boring technical wording. It should immediately capture attention and spark curiosity.\n"
            f"3. SCRIPT (TAMIL) & PACING (CRITICAL FOR VIEW RETENTION):\n"
            f"   - Hook (3s): Must start immediately with a shocking warning, critical mistake, or highly intriguing result (e.g. 'Stop doing this!', 'Don't make this huge mistake!'). Avoid slow build-ups or rhetorical questions.\n"
            f"   - Problem (5s max): Keep it extremely short (5 seconds max) explaining the risk.\n"
            f"   - Technical Solution (42-45s): Transition to the actual concrete, actionable steps and how-to guides (e.g. sand bed depth, exact calculations) within the first 8-10 seconds of the video so viewers don't swipe away.\n"
            f"   - The TOTAL narration must be approximately 55-60 seconds long when spoken (around 130-150 words). \n"
            f"   - CRITICAL: The narration text MUST strictly end with this exact Tamil CTA sentence: 'மேலும் பல சிவில் தகவல்களுக்கு Subscribe செய்யுங்கள்! உங்கள் கனவு இல்லத்திற்கு உடனே தொடர்பு கொள்ளுங்கள் - Kitchaa's Enterprises! முழு விவரங்கள் Description-ல் உள்ளது.'\n"
            f"4. VISUALS & TEXT OVERLAYS: Exactly 6 scenes total. For each scene, generate:\n"
            f"   - A 2-3 word English search keyword ('visual_query') for stock video search. Every query MUST contain a technical construction word (e.g., 'construction site', 'civil engineering', 'bridge work') to ensure Pexels doesn't return unrelated lifestyle footage.\n"
            f"   - A highly engaging, bold, short 2-4 word English phrase ('text_overlay') to appear on screen as a key visual cue (e.g., 'CRITICAL STEP', 'USE SAND BED', 'MISTAKE!', 'DO NOT DO THIS', 'BIG SAVINGS'). This keeps both local and global dubbed audiences highly hooked even without sound.\n"
            f"5. METADATA: Description MUST be generated strictly in English (not Tamil) and include Business Name, Contact, Website, Instagram, and all 4 services.\n"
            f"6. THUMBNAIL: Generate a simple, bold, high-click-through English text overlay for the thumbnail (max 3-4 words, capitalized, e.g. 'AVOID THIS MISTAKE', 'DON'T TILE YET', 'STOP DOING THIS').\n"
            f"7. SEO HASHTAGS (CRITICAL for 1M+ views): Use your search grounding tool to query Google/YouTube for the current daily trending and viral hashtags for civil engineering, house construction, home building, and YouTube Shorts in Tamil Nadu and India. Mix the live trending search results with:\n"
            f"   - Tamil viral tags: #தமிழ் #சிவில்_இன்ஜினியரிங் #கட்டுமானம் #வீடு_கட்டுவது_எப்படி #engineering\n"
            f"   - English trending: #civilengineering #construction #shorts #youtubeshorts #viral\n"
            f"   - Topic-specific: tags matching the exact topic being discussed\n"
            f"   - Broad reach: #india #tamil #tamilnadu #engineer #architecture #building #house\n"
            f"   - Business: #kitchaasenterprises #buildingconstruction #homeconstruction\n\n"
            f"OUTPUT FORMAT (JSON ONLY):\n"
            f"{{\n"
            f"  \"topic\": {{\"title_en\": \"...\", \"title_ta\": \"...\"}},\n"
            f"  \"script\": {{\n"
            f"    \"narration\": \"...\", \n"
            f"    \"scenes\": [\n"
            f"      {{\"visual_query\": \"...\", \"text_overlay\": \"...\"}},\n"
            f"      {{\"visual_query\": \"...\", \"text_overlay\": \"...\"}},\n"
            f"      {{\"visual_query\": \"...\", \"text_overlay\": \"...\"}},\n"
            f"      {{\"visual_query\": \"...\", \"text_overlay\": \"...\"}},\n"
            f"      {{\"visual_query\": \"...\", \"text_overlay\": \"...\"}},\n"
            f"      {{\"visual_query\": \"...\", \"text_overlay\": \"...\"}}\n"
            f"    ],\n"
            f"    \"metadata\": {{\n"
            f"      \"title\": \"... [Enter the optimized benefit-driven title here]\", \n"
            f"      \"description\": \"...\",\n"
            f"      \"tags\": [...],\n"
            f"      \"thumbnail_text\": \"... [Enter the bold 3-4 word thumbnail text here]\"\n"
            f"    }}\n"
            f"  }}\n"
            f"}}"
        )

        response_text = await self._generate_content(prompt)

        if not response_text:
            return None
            
        try:
            text = re.search(r'\{.*\}', response_text, re.DOTALL).group()
            data = json.loads(text)
            
            # === Post-validation: Enforce English title & description ===
            metadata = data.get('script', {}).get('metadata', {})
            title = metadata.get('title', '')
            description = metadata.get('description', '')
            
            def _has_tamil(s):
                """Check if string contains Tamil Unicode characters (U+0B80-U+0BFF)."""
                return bool(re.search(r'[\u0B80-\u0BFF]', s))
            
            if _has_tamil(title) or _has_tamil(description):
                logger.warning("Title or description contains Tamil text. Re-generating metadata in English...")
                fix_prompt = (
                    f"The following YouTube video metadata contains Tamil text. "
                    f"Rewrite ONLY the title and description in ENGLISH. Keep the same meaning.\n\n"
                    f"Current Title: {title}\n"
                    f"Current Description: {description}\n\n"
                    f"Output JSON ONLY: {{\"title\": \"...\", \"description\": \"...\"}}"
                )
                fix_response = await self._generate_content(fix_prompt)
                if fix_response:
                    try:
                        fix_text = re.search(r'\{.*\}', fix_response, re.DOTALL).group()
                        fix_data = json.loads(fix_text)
                        if fix_data.get('title') and not _has_tamil(fix_data['title']):
                            data['script']['metadata']['title'] = fix_data['title']
                            logger.info(f"Fixed title to English: {fix_data['title']}")
                        if fix_data.get('description') and not _has_tamil(fix_data['description']):
                            data['script']['metadata']['description'] = fix_data['description']
                            logger.info("Fixed description to English")
                    except Exception as fe:
                        logger.warning(f"English metadata fix parsing failed: {fe}")
            
            # Perform similarity check on the combined output
            similarity_score = await self.calculate_similarity(data['script'].get("narration", ""))
            data['script']["similarity_score"] = similarity_score
            
            threshold = settings.SIMILARITY_THRESHOLD or 0.7
            if similarity_score and similarity_score > threshold:
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
            "5. Title: Generate a highly intriguing, clear, benefit-driven YouTube title instead of only technical wording. "
            "6. Thumbnail: Generate a simple, bold, high-click-through English text overlay for the thumbnail (max 3-4 words, capitalized, e.g. 'AVOID THIS MISTAKE'). "
            "Provide ONLY valid JSON exactly matching this structure: "
            "{'narration': 'Full Tamil script here', "
            "'scenes': [{'visual_query': 'specific english search term for stock video'}], "
            "'metadata': {'title': '...', 'description': '...', 'tags': [...], 'thumbnail_text': '...'}} "
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
                if not past.script_text:
                    continue
                old_words = set(re.findall(r'\w+', past.script_text.lower()))
                intersection = new_words.intersection(old_words)
                union = new_words.union(old_words)
                sim = len(intersection) / len(union) if union else 0
                max_similarity = max(max_similarity, sim)
            
            return max_similarity
                
if __name__ == "__main__":
    # Local Test Script
    import asyncio
    from dotenv import load_dotenv
    load_dotenv() # Load your .env file
    
    async def test():
        logging.basicConfig(level=logging.INFO)
        print("Starting Gemini Script Generation Test...")
        
        # Connect to DB for similarity check
        Database.connect()
        
        engine = ScriptEngine()
        
        try:
            result = await engine.generate_full_content()
            if result:
                print("\nSUCCESS! Generated Content:")
                print(f"Topic: {result['topic']['title_en']}")
                print(f"Script Snippet: {result['script']['narration'][:100]}...")
            else:
                print("\nFAILED: Engine returned None")
        except Exception as e:
            print(f"\nCRITICAL ERROR: {e}")
        finally:
            await Database.close()

    asyncio.run(test())
