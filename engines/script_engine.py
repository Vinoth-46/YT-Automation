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
            f"Goal: Generate a unique topic AND a high-retention 25 to 35-second script.\n\n"
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
            f"2. TITLE: Generate a highly intriguing, clear, benefit-driven YouTube title (e.g. 'Why Your Bathroom Floor Is Lower (Must-Know Tip Before Tiling)' or 'Avoid This Huge Foundation Mistake!') instead of boring technical wording. It should immediately capture attention and spark curiosity. DO NOT start the title with 'STOP!' — vary your title hooks using different starting words like 'Avoid...', 'Why...', 'Never...', 'The Secret of...', 'Before You...', 'How to...' to ensure diversity. DO NOT include raw hashtags in the title.\n"
            f"3. SCRIPT (TAMIL) & PACING (CRITICAL FOR HIGH VIEW RETENTION):\n"
            f"   - HOOK (first 3 seconds — MOST IMPORTANT LINE IN THE ENTIRE VIDEO):\n"
            f"     * MUST be a HARD PUNCH — a shocking statistic, a devastating mistake people make, or a surprising fact.\n"
            f"     * EXAMPLES OF GOOD HOOKS: '90% of Tamil Nadu homes have this foundation mistake!', 'This one tiling error costs ₹50,000 to fix!', 'Engineers hide this secret from home owners!'\n"
            f"     * BANNED OPENINGS: Rhetorical questions ('Did you know?', 'Have you ever?'), slow greetings, brand introductions in the first line.\n"
            f"     * DO NOT start with 'Stop!', 'Nillungal!', or any variation of 'stop'.\n"
            f"   - Problem (4-5s max): Keep it extremely short explaining the risk.\n"
            f"   - Technical Solution (15-20s): Transition immediately to concrete, actionable steps so viewers don't swipe away.\n"
            f"   - SCRIPT LENGTH: The TOTAL narration must be approximately 25-35 seconds long when spoken (around 60-75 Tamil words total across 4 scenes).\n"
            f"   - CRITICAL: The narration text MUST strictly end with this exact concise Tamil CTA: 'மேலும் பல சிவில் தகவல்களுக்கு Subscribe செய்யுங்கள்! Kitchaa\'s Enterprises.'\n"
            f"4. VISUALS & SCENES: Exactly 4 scenes total. Every scene MUST depict a 100% concrete, physical, tangible construction action or building object:\n"
            f"   - STRICT ZERO-TOLERANCE RULE: NEVER depict people talking to camera, pointing, waving, running, jumping, walking, fitness, business meetings, holding smartphones, or clicking subscribe buttons.\n"
            f"   - Scene 1 (Hook): Must physically depict the structural defect or construction site action (e.g. 'cracked concrete foundation', 'water leaking wall dampness', 'foundation digging'). DO NOT depict a person looking worried or talking.\n"
            f"   - Scene 2 (Problem/Analysis): Must physically depict materials or structural components (e.g. 'mixing mortar cement', 'red clay bricks inspection', 'measuring tape on column').\n"
            f"   - Scene 3 (Technical Solution): Must physically depict the correct engineering work being done (e.g. 'mason laying bricks with trowel', 'applying waterproof coating to wall', 'vibrating wet concrete in slab').\n"
            f"   - Scene 4 (CTA / Outro): Must physically depict a completed, modern, beautiful house or pristine construction finish (e.g. 'exterior of modern Indian residential home in sunlight', 'smooth painted wall finish'). DO NOT depict a subscribe button or people waving.\n"
            f"   - 'visual_query': An exact 2-3 word English search term strictly chosen from physical construction vocabulary (e.g. 'pouring concrete', 'laying bricks', 'wall plastering', 'mixing cement', 'digging foundation', 'tiling floor'). NEVER include abstract words ('mistake', 'tips', 'problem', 'secret', 'solution', 'subscribe', 'engineering').\n"
            f"   - 'ai_video_prompt': A direct 20-30 word camera-directed physical shot for AI video generators (e.g. 'Cinematic close-up tracking shot of a mason using a metal trowel to lay mortar between red bricks, photorealistic, 4k'). Format: [Camera Angle] of [Physical Action / Object], [Lighting/Quality].\n"
            f"   - 'narration_tamil': The exact Tamil script segment spoken during this specific scene (approx 15-20 words). The concatenation of all 4 'narration_tamil' blocks must equal the overall 'narration' block.\n"
            f"   - ANIMATION: Do NOT generate animation overlays. Set \"animation\": null for all scenes.\n"
            f"5. METADATA: Description MUST be generated strictly in English (not Tamil) and include Business Name, Contact, Website, Instagram, and all 4 services.\n"
            f"6. THUMBNAIL: Generate a simple, bold, high-click-through English text overlay for the thumbnail (max 3-4 words, capitalized, e.g. 'AVOID THIS MISTAKE', 'DON'T TILE YET', 'NEVER DO THIS'). DO NOT start the thumbnail text with 'STOP!'.\n"
            f"7. SEO HASHTAGS (CRITICAL for Shorts algorithm): Generate 5-8 focused hashtags max. Do NOT overstuff tags. Include: #Shorts, #CivilEngineering, #Tamil, #HomeConstruction, and 1-2 topic-specific tags.\n\n"
            f"OUTPUT FORMAT (JSON ONLY):\n"
            f"{{\n"
            f"  \"topic\": {{\"title_en\": \"...\", \"title_ta\": \"...\"}},\n"
            f"  \"script\": {{\n"
            f"    \"narration\": \"Full combined Tamil script here (concatenation of all 4 narration_tamil fields)\", \n"
            f"    \"scenes\": [\n"
            f"      {{\"visual_query\": \"...\", \"ai_video_prompt\": \"Detailed photorealistic prompt for AI generator\", \"text_overlay\": \"...\", \"narration_tamil\": \"Tamil narration spoken during scene 1 (approx 15-20 words)\", \"animation\": null}},\n"
            f"      {{\"visual_query\": \"...\", \"ai_video_prompt\": \"Detailed photorealistic prompt for AI generator\", \"text_overlay\": \"...\", \"narration_tamil\": \"Tamil narration spoken during scene 2 (approx 15-20 words)\", \"animation\": null}},\n"
            f"      {{\"visual_query\": \"...\", \"ai_video_prompt\": \"Detailed photorealistic prompt for AI generator\", \"text_overlay\": \"...\", \"narration_tamil\": \"Tamil narration spoken during scene 3 (approx 15-20 words)\", \"animation\": null}},\n"
            f"      {{\"visual_query\": \"...\", \"ai_video_prompt\": \"Detailed photorealistic prompt for AI generator\", \"text_overlay\": \"...\", \"narration_tamil\": \"Tamil narration spoken during scene 4 (approx 15-20 words)\", \"animation\": null}}\n"
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
            
            # Sanitize scene prompts to guarantee 100% physical relevance
            if "scenes" in data.get('script', {}):
                data['script']['scenes'] = self._sanitize_scene_prompts(
                    data['script']['scenes'], 
                    data.get('topic', {}).get('title_en', 'house construction')
                )

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


    def _sanitize_scene_prompts(self, scenes, fallback_topic="house construction"):
        """Enforce strictly physical construction visuals and eliminate abstract or irrelevant keywords."""
        banned_abstract = [
            'mistake', 'problem', 'tips', 'tip', 'secret', 'solution', 'subscribe', 
            'human', 'man', 'person', 'woman', 'advice', 'warning', 'error', 'danger', 
            'careful', 'idea', 'rule', 'hack', 'safety', 'presentation', 'explaining',
            'running', 'walking', 'jumping', 'talking', 'confused', 'smiling', 'gesture',
            'phone', 'button', 'click', 'subscribe button', 'meeting'
        ]
        
        fallback_queries = [
            "foundation concrete pouring",
            "laying red clay bricks",
            "mortar plastering wall",
            "modern residential house exterior"
        ]
        
        for idx, sc in enumerate(scenes):
            vq = sc.get("visual_query", "").strip()
            vq_lower = vq.lower()
            words = re.findall(r'\b\w+\b', vq_lower)
            
            # If visual_query is missing or heavily abstract or contains banned words
            if not vq or any(b in words for b in banned_abstract) or len(words) < 2:
                clean_vq = fallback_queries[idx % len(fallback_queries)]
                logger.info(f"Sanitized scene {idx+1} visual_query: '{vq}' -> '{clean_vq}'")
                sc["visual_query"] = clean_vq
            elif not any(term in vq_lower for term in ["construction", "building", "brick", "concrete", "wall", "foundation", "cement", "tile", "mortar", "slab", "house", "plaster", "rebar", "roof"]):
                sc["visual_query"] = f"{vq} construction"
                
            ai_prompt = sc.get("ai_video_prompt", "").strip()
            ai_words = set(re.findall(r'\b\w+\b', ai_prompt.lower()))
            has_banned_concept = bool(ai_words.intersection(banned_abstract)) or any(phrase in ai_prompt.lower() for phrase in ["talking to camera", "pointing at", "clicking subscribe", "warning homeowner", "explaining mistake", "subscribe button", "waving", "thumbs up", "looking at camera"])
            
            # Clean AI prompt from non-physical/talking head elements
            if not ai_prompt or has_banned_concept:
                if idx == 0:
                    sc["ai_video_prompt"] = "Cinematic dramatic close-up shot of cracked concrete foundation structure, photorealistic 4k"
                elif idx == len(scenes) - 1:
                    sc["ai_video_prompt"] = "Cinematic exterior drone tracking shot of modern luxury Indian residential house in morning sunlight, photorealistic 4k"
                else:
                    sc["ai_video_prompt"] = f"Cinematic close-up tracking shot of {sc['visual_query']}, professional lighting, photorealistic 4k"
        return scenes

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
            "4. Exactly 6 scenes total. Every scene MUST depict a 100% concrete, physical construction action (NO talking heads, running, jumping, walking). "
            "5. Title: Generate a highly intriguing, clear, benefit-driven YouTube title instead of only technical wording. "
            "6. Thumbnail: Generate a simple, bold, high-click-through English text overlay for the thumbnail (max 3-4 words, capitalized, e.g. 'AVOID THIS MISTAKE'). "
            "Provide ONLY valid JSON exactly matching this structure: "
            "{"
            "  \"narration\": \"Full Tamil script here (concatenation of all narration_tamil fields)\", "
            "  \"scenes\": [{\"visual_query\": \"specific physical english search term for stock video (e.g. laying bricks, concrete pouring)\", \"ai_video_prompt\": \"Cinematic close-up of physical construction action without people talking\", \"narration_tamil\": \"Tamil narration spoken during this scene\", \"animation\": null}], "
            "  \"metadata\": {\"title\": \"...\", \"description\": \"...\", \"tags\": [...], \"thumbnail_text\": \"...\"}"
            "} "
            "Make sure 'visual_query' is a highly specific, descriptive 2-3 word English search keyword that represents a concrete, physical, visual action or object that can be filmed. "
            "Set 'animation': null for all scenes (no animation overlays). Add a 'narration_tamil' string block inside each scene representing the specific Tamil script spoken during that scene. Also generate a detailed 'ai_video_prompt' describing the photorealistic scene construction actions and camera movement for each scene."
        )

        response_text = await self._generate_content(prompt)
        if not response_text:
            return None
        try:
            text = re.search(r'\{.*\}', response_text, re.DOTALL).group()
            script_data = json.loads(text)
            
            # Sanitize scene prompts to guarantee 100% physical relevance
            if "scenes" in script_data:
                script_data["scenes"] = self._sanitize_scene_prompts(
                    script_data["scenes"],
                    topic.get('title_en', 'house construction')
                )

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
