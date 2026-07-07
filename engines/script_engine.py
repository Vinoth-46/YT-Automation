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
        self.model_name = 'gemini-2.5-flash'
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
        """Make an async request to Gemini API with retries, key rotation, search-grounding fallback, and delay."""
        models_to_try = [
            'gemini-2.5-flash',           # Primary: fast and capable
            'gemini-2.0-flash',           # Fallback 1: stable and fast
            'gemini-2.5-flash-preview-05-20',  # Fallback 2: latest preview build
            'gemini-2.0-flash-lite',      # Fallback 3: lightweight, rarely rate-limited
            'gemini-2.5-pro'              # Fallback 4: most capable but heavy quota usage
        ]
        
        for model in models_to_try:
            # We will try both with and without search grounding if needed
            for use_search in [True, False]:
                logger.info(f"Attempting content generation with {model} (Google Search Grounding: {use_search})...")
                
                # Loop through key index offset to make sure we try all keys
                for key_offset in range(len(self.api_keys)):
                    # Rotate to next key for each attempt if we aren't on the first key of this stage
                    if key_offset > 0:
                        self._rotate_key()
                        
                    for attempt in range(max_retries):
                        try:
                            # Configure tools depending on search fallback
                            tools = [types.Tool(google_search=types.GoogleSearch())] if use_search else None
                            
                            response = await asyncio.wait_for(
                                asyncio.to_thread(
                                    self.client.models.generate_content,
                                    model=model,
                                    contents=prompt,
                                    config=types.GenerateContentConfig(
                                        temperature=0.9,
                                        tools=tools
                                    )
                                ),
                                timeout=60
                            )
                            logger.info(f"🎉 Gemini API success with model {model} (Search: {use_search}) using Key #{self.current_key_index + 1}")
                            return response.text
                        except asyncio.TimeoutError:
                            logger.warning(f"Job timed out generating script with {model} (Search: {use_search}) on attempt {attempt+1}. Retrying...")
                            continue
                        except Exception as e:
                            error_str = str(e).lower()
                            logger.warning(f"Error calling {model} on attempt {attempt+1}: {error_str}")
                            
                            # Check for rate limit or quota errors
                            if "429" in error_str or "quota" in error_str or "exhausted" in error_str:
                                # Switch key and retry immediately within the key loop
                                logger.warning(f"Rate limit / quota hit for {model} with Key #{self.current_key_index + 1}.")
                                if len(self.api_keys) > 1 and key_offset < len(self.api_keys) - 1:
                                    logger.info("Rotating key to try again immediately...")
                                    break # break out of the attempt loop to move to the next key_offset
                                else:
                                    # We have exhausted all keys for this configuration.
                                    # Let's wait a bit before moving to the next model or next configuration
                                    wait_sec = 10
                                    logger.info(f"All keys exhausted for {model}. Sleeping for {wait_sec}s...")
                                    await asyncio.sleep(wait_sec)
                                    break
                            else:
                                # Non-429 error (e.g. 503 service unavailable or connection issues)
                                wait_time = (2 ** attempt) * 5  # 5s, 10s, 20s
                                logger.warning(f"Retrying in {wait_time}s due to non-429 error...")
                                await asyncio.sleep(wait_time)
                                
        logger.error("❌ All Gemini API models, search modes, and keys failed.")
        return None

    async def generate_full_content(self, existing_topics=None, custom_topic=None):
        """Mega-Prompt: Generate Topic and Script with Kitchaa's Enterprises branding.
        Trending topics from YouTube autocomplete are injected to maximise relevance.
        """
        # ── Fetch trending search terms (non-blocking — fails silently) ───────────────
        trending_terms = []
        try:
            from engines.trends_engine import get_trending_topics
            trending_terms = await asyncio.wait_for(get_trending_topics(max_results=8), timeout=15)
        except Exception as te:
            logger.warning(f"Trending topics fetch skipped: {te}")
        
        trending_block = ""
        if trending_terms:
            bullets = "\n".join(f"  • {t}" for t in trending_terms)
            trending_block = (
                f"\n🟢 CURRENTLY TRENDING on YouTube/Google (use these as INSPIRATION for your topic — pick or remix the most relevant one):\n"
                f"{bullets}\n"
                f"If none are civil-engineering related, ignore them and pick your own fresh topic.\n"
            )
            logger.info(f"Injected {len(trending_terms)} trending terms into prompt")

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
            f"🔴 CRITICAL TARGET AUDIENCE & LOCALIZATION: The target audience is strictly in India (specifically Tamil Nadu). "
            f"The generated topic and script MUST be highly relevant to Indian house construction, Indian residential building practices, "
            f"local Indian civil engineering hacks, local Indian building materials (e.g., M-sand vs river sand, red clay bricks, hollow blocks, Indian cement brands), "
            f"hot Indian climate considerations, and Vastu Shastra (traditional Indian architecture). "
            f"Do NOT generate content about foreign architectures (like Burj Khalifa, foreign suspension bridges, or US/European wooden frame houses). "
            f"Focus on common concrete, brick, tiling, waterproofing, and structural tips for mid-sized Indian residential homes.\n\n"
            f"{trending_block}"
            f"🔴 PREVIOUS TOPICS BLACKLIST (DO NOT REPEAT OR MIMIC THESE):\n"
            f"{history_text or 'None'}\n\n"
            f"BRANDING REQUIREMENTS (Kitchaa's Enterprises):\n"
            f"{business_details}\n\n"
            f"INSTRUCTIONS:\n"
            f"1. TOPIC: {topic_instruction}\n"
            f"2. TITLE: Generate a highly intriguing, clear, benefit-driven YouTube title (e.g. 'Why Your Bathroom Floor Is Lower (Must-Know Tip Before Tiling)' or 'Avoid This Huge Foundation Mistake!') instead of only boring technical wording. It should immediately capture attention and spark curiosity. DO NOT start the title with 'STOP!' — vary your title hooks using different starting words like 'Avoid...', 'Why...', 'Never...', 'The Secret of...', 'Before You...', 'How to...' to ensure diversity.\n"
            f"3. SCRIPT (TAMIL) & PACING (CRITICAL FOR VIEW RETENTION):\n"
            f"   - HOOK (first 3 seconds — MOST IMPORTANT LINE IN THE ENTIRE VIDEO):\n"
            f"     * MUST be a HARD PUNCH — a shocking statistic, a devastating mistake people make, or a surprising fact.\n"
            f"     * EXAMPLES OF GOOD HOOKS: '90% of Tamil Nadu homes have this foundation mistake!', 'This one tiling error costs ₹50,000 to fix!', 'Engineers hide this secret from home owners!'\n"
            f"     * BANNED OPENINGS: Rhetorical questions ('Did you know?', 'Have you ever?'), slow greetings, brand introductions in the first line.\n"
            f"     * DO NOT start with 'Stop!', 'Nillungal!', or any variation of 'stop'.\n"
            f"   - Problem (5s max): Keep it extremely short (5 seconds max) explaining the risk.\n"
            f"   - Technical Solution (42-45s): Transition to the actual concrete, actionable steps and how-to guides (e.g. sand bed depth, exact calculations) within the first 8-10 seconds of the video so viewers don't swipe away.\n"
            f"   - The TOTAL narration must be approximately 55-60 seconds long when spoken (around 130-150 words). \n"
            f"   - CRITICAL: The narration text MUST strictly end with this exact Tamil CTA sentence: 'மேலும் பல சிவில் தகவல்களுக்கு Subscribe செய்யுங்கள்! உங்கள் கனவு இல்லத்திற்கு உடனே தொடர்பு கொள்ளுங்கள் - Kitchaa's Enterprises! முழு விவரங்கள் Description-ல் உள்ளது.'\n"
            f"4. VISUALS & SCENES: Exactly 6 scenes total. For each scene, generate:\n"
            f"   - An extremely specific, descriptive 2-3 word English search keyword ('visual_query') for stock video search. It MUST represent a concrete, physical, visual action or object that can be filmed (e.g., 'concrete pouring', 'laying bricks', 'painting wall', 'mixing cement', 'digging foundation'). Do NOT use abstract concepts (e.g., 'mistake', 'Vastu', 'assistance', 'problem', 'engineering', 'safety') or general terms like 'construction site' because search engines (Pexels, Pixabay) cannot find relevant video clips for abstract concepts. Keep it simple and physical.\n"
            f"   - A short helper visual description phrase ('text_overlay') in English (max 2-3 words, e.g. 'POURING CONCRETE', 'LAYING BRICKS', 'PAINTING WALL') to describe the visual context.\n"
            f"   - ANIMATION (MANDATORY for 4 out of 6 scenes): You MUST include an 'animation' block for scenes 2, 3, 4, and 5 (the educational/technical scenes). Do NOT add animation to Scene 1 (hook — keep it clean for retention) or Scene 6 (CTA — keep it clean for the subscribe message). Each animation creates a moving 2D infographic overlay. Choose one type per scene:\n"
            f"     * Comparison: {{\"type\": \"comparison\", \"title\": \"M-Sand vs River Sand\", \"details\": {{\"item_a\": \"M-Sand\", \"item_b\": \"River Sand\", \"points_a\": [\"Angular shape\", \"No silt content\"], \"points_b\": [\"Rounded shape\", \"Contains silt\"]}}}}\n"
            f"     * Concrete/mortar ratio: {{\"type\": \"ratio\", \"title\": \"M20 Concrete\", \"details\": {{\"mix_name\": \"M20 Concrete\", \"ratio\": \"1:1.5:3\", \"ingredients\": [{{\"name\": \"Cement\", \"parts\": 1.0, \"color\": \"grey\"}}, {{\"name\": \"Sand\", \"parts\": 1.5, \"color\": \"yellow\"}}, {{\"name\": \"Aggregate\", \"parts\": 3.0, \"color\": \"dark_grey\"}}]}}}}\n"
            f"     * Structural blueprint: {{\"type\": \"structural\", \"title\": \"Foundation footing\", \"details\": {{\"diagram_type\": \"footing|brick_wall\", \"labels\": [{{\"text\": \"Ground level\", \"x\": 540, \"y\": 700}}, {{\"text\": \"Concrete bed\", \"x\": 540, \"y\": 980}}]}}}}\n"
            f"     * Progress/Time tracking: {{\"type\": \"progress\", \"title\": \"Curing Curing\", \"details\": {{\"target_label\": \"Curing Time\", \"value\": \"7 Days\", \"milestones\": [\"Day 3: 50% Strength\", \"Day 7: 70% Strength\"]}}}}\n"
            f"     * Warning/Defect alert: {{\"type\": \"warning\", \"title\": \"Avoid Cracks\", \"details\": {{\"defect_name\": \"Shrinkage Cracks\", \"consequence\": \"Water leakage\", \"fix\": \"Keep concrete wet\"}}}}\n"
            f"5. METADATA: Description MUST be generated strictly in English (not Tamil) and include Business Name, Contact, Website, Instagram, and all 4 services. Also, generate highly professional, clickable translations of the title and description in Hindi and Spanish to target North India and Global Spanish-speaking markets.\n"
            f"6. THUMBNAIL: Generate a simple, bold, high-click-through English text overlay for the thumbnail (max 3-4 words, capitalized, e.g. 'AVOID THIS MISTAKE', 'DON'T TILE YET', 'NEVER DO THIS'). DO NOT start the thumbnail text with 'STOP!'.\n"
            f"7. SEO HASHTAGS (CRITICAL for 100K+ views): Generate 20-25 hashtags optimized for YouTube Shorts discovery. Use your search grounding tool to query Google/YouTube for TODAY's trending and viral hashtags for civil engineering, house construction, home building, and YouTube Shorts in Tamil Nadu and India. Your tags MUST include:\n"
            f"   - Shorts algorithm: #Shorts #youtubeshorts #viral #trending #fyp #viralshorts\n"
            f"   - Tamil viral tags: #tamil #tamilnadu #tamilvlog #tamilshorts #civilengineeringtamil #வீடுகட்டுவதுஎப்படி #சிவில்_இன்ஜினியரிங் #கட்டுமானம்\n"
            f"   - English high-volume: #civilengineering #construction #homeconstruction #buildingconstruction #concrete #housebuilding #architecture #engineering\n"
            f"   - Topic-specific: 3-5 tags matching the exact topic discussed (e.g., #concreteratio #M20concrete #foundationtips)\n"
            f"   - Geo reach: #india #tamilnadu #chennai #southindia\n"
            f"   - Business: #kitchaasenterprises\n\n"
            f"OUTPUT FORMAT (JSON ONLY):\n"
            f"{{\n"
            f"  \"topic\": {{\"title_en\": \"...\", \"title_ta\": \"...\"}},\n"
            f"  \"script\": {{\n"
            f"    \"narration\": \"...\", \n"
            f"    \"scenes\": [\n"
            f"      {{\"visual_query\": \"...\", \"text_overlay\": \"...\", \"animation\": {{\"type\": \"...\", \"title\": \"...\", \"details\": {{...}}}}}},\n"
            f"      {{\"visual_query\": \"...\", \"text_overlay\": \"...\", \"animation\": {{\"type\": \"...\", \"title\": \"...\", \"details\": {{...}}}}}},\n"
            f"      {{\"visual_query\": \"...\", \"text_overlay\": \"...\", \"animation\": {{\"type\": \"...\", \"title\": \"...\", \"details\": {{...}}}}}},\n"
            f"      {{\"visual_query\": \"...\", \"text_overlay\": \"...\", \"animation\": {{\"type\": \"...\", \"title\": \"...\", \"details\": {{...}}}}}},\n"
            f"      {{\"visual_query\": \"...\", \"text_overlay\": \"...\", \"animation\": {{\"type\": \"...\", \"title\": \"...\", \"details\": {{...}}}}}},\n"
            f"      {{\"visual_query\": \"...\", \"text_overlay\": \"...\", \"animation\": {{\"type\": \"...\", \"title\": \"...\", \"details\": {{...}}}}}}\n"
            f"    ],\n"
            f"    \"metadata\": {{\n"
            f"      \"title\": \"... [Enter the optimized benefit-driven title here]\", \n"
            f"      \"description\": \"...\",\n"
            f"      \"tags\": [...],\n"
            f"      \"thumbnail_text\": \"... [Enter the bold 3-4 word thumbnail text here]\",\n"
            f"      \"hindi_title\": \"... [Clickable translation in Hindi]\",\n"
            f"      \"hindi_description\": \"... [Description translation in Hindi]\",\n"
            f"      \"spanish_title\": \"... [Clickable translation in Spanish]\",\n"
            f"      \"spanish_description\": \"... [Description translation in Spanish]\"\n"
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
        """Generate a fresh civil engineering topic tailored for India."""
        prompt = (
            "Generate a unique and highly engaging civil engineering topic for a 120-second YouTube Short. "
            "The topic MUST be strictly relevant to Indian residential house construction, Indian local building materials, "
            "Indian structural hacks, and home building in India/Tamil Nadu. Focus on practical concrete, bricks, foundation, waterproofing, Vastu, or cost-saving tips. "
            "Do NOT focus on foreign skyscrapers or wooden frame construction. "
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
            "{"
            "  \"narration\": \"Full Tamil script here\", "
            "  \"scenes\": [{\"visual_query\": \"specific english search term for stock video\", \"animation\": {\"type\": \"comparison|ratio|structural|progress|warning\", \"title\": \"...\", \"details\": {}}}], "
            "  \"metadata\": {\"title\": \"...\", \"description\": \"...\", \"tags\": [...], \"thumbnail_text\": \"...\"}"
            "} "
            "Make sure 'visual_query' is a highly specific, descriptive 2-3 word English search keyword that represents a concrete, physical, visual action or object that can be filmed. "
            "IMPORTANT: You MUST include an 'animation' block for scenes 2, 3, 4, and 5 (skip scene 1 hook and scene 6 CTA). Include the correct type and structured details (e.g. comparison points, concrete ratio cups, structural drawing coordinates, curing days progress, or warning descriptions)."
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
