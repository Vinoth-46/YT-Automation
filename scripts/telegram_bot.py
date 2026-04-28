"""
Interactive Telegram Production Control Center (Daily Mode)
Handles on-demand generation of 1 video per day, previews, SEO approvals, and YouTube uploads.
"""

import json
import logging
import sys
import threading
import traceback
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

# Import pipeline functions
from scripts.script_generator import generate_scripts
from scripts.visual_planner import generate_visual_plans
from main import generate_day
from scripts.youtube_uploader import upload_video
from scripts.seo_expert import optimize_seo

logger = logging.getLogger(__name__)

# --- Bot State Management ---
def load_state():
    if config.BOT_STATE_FILE.exists():
        return json.loads(config.BOT_STATE_FILE.read_text(encoding="utf-8"))
    return {
        "video_mode": config.VIDEO_MODE,
        "awaiting_feedback": False,
        "seo_cache": {}
    }

def save_state(state):
    config.BOT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.BOT_STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


class ProductionBot:
    def __init__(self):
        self.state = load_state()
        
        if not config.TELEGRAM_BOT_TOKEN:
            logger.error("❌ TELEGRAM_BOT_TOKEN is MISSING in environment variables!")
            raise ValueError("TELEGRAM_BOT_TOKEN not found. Did you set it in Hugging Face Secrets?")

        # Use a proxy base URL because api.telegram.org is unreachable from this HF node
        # Added trailing slash to ensure correct URL concatenation
        proxy_url = "https://tbot.xyz/bot/" 
        
        self.app = (
            Application.builder()
            .token(config.TELEGRAM_BOT_TOKEN)
            .base_url(proxy_url)
            .connect_timeout(30)
            .read_timeout(30)
            .write_timeout(30)
            .pool_timeout(30)
            .build()
        )
        self.chat_id = config.TELEGRAM_CHAT_ID

        # Register Handlers
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))

    async def _send_msg(self, text, reply_markup=None):
        if not self.chat_id:
            logger.error("Chat ID not configured!")
            return
        try:
            await self.app.bot.send_message(
                chat_id=self.chat_id, 
                text=text, 
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send msg: {e}")

    # --- Commands ---
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("🎬 Generate Today's Video", callback_data="ask_mode")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"🚀 *Kitcha Enterprises Production Bot*\n\n"
            f"I am ready to generate today's video!\n"
            f"Click the button below to start.",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

    # --- Callbacks ---
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        try:
            await query.answer()
        except Exception as e:
            logger.warning(f"Could not answer callback query: {e}")
            
        data = query.data

        if data == "ask_mode":
            keyboard = [
                [InlineKeyboardButton("🎭 Avatar + Footage", callback_data="mode_avatar")],
                [InlineKeyboardButton("🎬 Footage Only", callback_data="mode_footage_only")]
            ]
            await query.edit_message_text(
                "How do you want today's video generated?", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        elif data.startswith("mode_"):
            mode = data.replace("mode_", "")
            self.state["video_mode"] = mode
            save_state(self.state)
            
            await query.edit_message_text(
                f"✅ Mode set to: *{mode.replace('_', ' ').title()}*\n"
                f"⏳ Step 1: Generating AI Script...", 
                parse_mode="Markdown"
            )
            # Run the single-day generation in a background thread
            threading.Thread(target=self._run_daily_pipeline_blocking, args=(False, query.message.message_id)).start()

        elif data == "video_approve":
            await query.edit_message_text("✅ Video approved! Generating SEO tags...")
            threading.Thread(target=self._generate_seo_blocking).start()

        elif data == "video_reject":
            self.state["awaiting_feedback"] = True
            save_state(self.state)
            await query.edit_message_text(
                "❌ Video rejected.\n*Please type what needs to be fixed* (e.g. 'Avatar looks weird', 'Change the background').", 
                parse_mode="Markdown"
            )

        elif data == "seo_approve":
            await query.edit_message_text("✅ SEO Approved! Uploading to YouTube now...")
            threading.Thread(target=self._upload_video_blocking).start()

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        if self.state.get("awaiting_feedback"):
            self.state["awaiting_feedback"] = False
            save_state(self.state)
            
            await update.message.reply_text(f"🔄 Regenerating today's video with feedback: '{text}'...")
            # We don't have an inline message to edit here, so we pass None
            threading.Thread(target=self._run_daily_pipeline_blocking, args=(True, None)).start()

    # --- Blocking Pipeline Runners (run in threads) ---
    def _run_daily_pipeline_blocking(self, force: bool, message_id: int = None):
        """Generates exactly 1 script and 1 video."""
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        if config.RENDER_LOCK.locked():
            loop.run_until_complete(self._send_msg("⚠️ *A video is already being generated.* Please wait a moment..."))
            loop.close()
            return

        try:
            with config.RENDER_LOCK:
                # Step 1: Generate 1 Script (TOTAL_DAYS is set to 1 in config.py)
                scripts = generate_scripts(force_regenerate=True)
                if not scripts:
                    loop.run_until_complete(self._send_msg("❌ Failed to generate script from LLM."))
                    return
                    
                if message_id:
                    try:
                        loop.run_until_complete(self.app.bot.edit_message_text(
                            chat_id=self.chat_id,
                            message_id=message_id,
                            text="⏳ Step 2: Generating Visuals & Voiceover...",
                            parse_mode="Markdown"
                        ))
                    except Exception:
                        pass

                # Step 2: Generate visual plan for that 1 script
                visual_plans = generate_visual_plans(scripts, force_regenerate=True)
                
                if message_id:
                    try:
                        loop.run_until_complete(self.app.bot.edit_message_text(
                            chat_id=self.chat_id,
                            message_id=message_id,
                            text="⏳ Step 3: Rendering Final Video (ETA: ~2 minutes) 🕒...",
                            parse_mode="Markdown"
                        ))
                    except Exception:
                        pass

                # Use global config for VIDEO_MODE temporarily
                original_mode = getattr(config, "VIDEO_MODE", "avatar")
                config.VIDEO_MODE = self.state.get("video_mode", "avatar")
                
                # Step 3: Generate the video (Day 1)
                video_path = generate_day(1, scripts, visual_plans, force=True)
                
                # Restore mode
                config.VIDEO_MODE = original_mode

                if video_path and video_path.exists():
                    # Send Video Preview
                    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                    keyboard = [
                        [InlineKeyboardButton("✅ Approve", callback_data="video_approve"),
                         InlineKeyboardButton("❌ Reject", callback_data="video_reject")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    with open(video_path, 'rb') as video_file:
                        loop.run_until_complete(self.app.bot.send_video(
                            chat_id=self.chat_id,
                            video=video_file,
                            caption=f"🎥 *Today's Video Preview*\nReview the generated video:",
                            parse_mode="Markdown",
                            reply_markup=reply_markup,
                            write_timeout=120,
                            read_timeout=120,
                            connect_timeout=120
                        ))
                else:
                    loop.run_until_complete(self._send_msg(f"❌ Video generation failed."))

        except Exception as e:
            import traceback
            logger.error(traceback.format_exc())
            try:
                loop.run_until_complete(self._send_msg(f"❌ Exception in pipeline: {str(e)[:200]}"))
            except Exception:
                pass
        finally:
            try:
                loop.close()
            except Exception:
                pass

    def _generate_seo_blocking(self):
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            scripts = generate_scripts()
            script = scripts[0] # Day 1 script
            
            seo_data = optimize_seo(script.get("script", script.get("hook", "")), script.get("topic", ""))
            
            self.state["seo_cache"] = seo_data
            save_state(self.state)
            
            msg = (
                f"📈 *SEO Metadata*\n\n"
                f"*Title:* {seo_data.get('seo_title')}\n"
                f"*Hashtags:* {' '.join(seo_data.get('hashtags', []))}\n"
                f"*Description:*\n{seo_data.get('description')}\n\n"
                "Do you want to upload with this metadata?"
            )
            
            keyboard = [
                [InlineKeyboardButton("✅ Upload to YouTube", callback_data="seo_approve")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            loop.run_until_complete(self._send_msg(msg, reply_markup=reply_markup))
            loop.close()
        except Exception as e:
            logger.error(traceback.format_exc())
            loop.run_until_complete(self._send_msg(f"❌ SEO generation failed: {e}"))

    def _upload_video_blocking(self):
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            loop.run_until_complete(self._send_msg("📤 Uploading to YouTube..."))
            
            video_path = config.OUTPUT_DIR / f"day_01" / "final_video.mp4"
            seo_data = self.state.get("seo_cache", {})
            
            # Combine generated description with default footer
            full_desc = f"{seo_data.get('description', '')}\n\n"
            full_desc += f"{' '.join(seo_data.get('hashtags', []))}\n\n"
            full_desc += f"© {config.CHANNEL_NAME}"
            
            result = upload_video(
                video_path=video_path,
                title=seo_data.get('seo_title', f"Civil Engineering Tips #Shorts"),
                description=full_desc,
                tags=seo_data.get('hashtags', []),
                publish_at=None 
            )
                
            loop.run_until_complete(self._send_msg(f"🎉 *Successfully Uploaded!*\n🔗 [Watch on YouTube]({result['url']})"))
            loop.close()
        except Exception as e:
            logger.error(traceback.format_exc())
            loop.run_until_complete(self._send_msg(f"❌ Upload failed: {e}"))


# Dummy bot instance for external imports (like main.py) that expect a `bot.send_message`
class DummyBot:
    def log_to_telegram(self, status):
        pass
    def notify_video_ready(self, day, url=None):
        pass
    def send_message(self, text):
        pass
        
bot = DummyBot()

def main():
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not found in .env!")
        return
        
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logger.info("Starting Telegram Production Bot (Daily Mode)...")
    
    prod_bot = ProductionBot()
    prod_bot.app.run_polling()

if __name__ == '__main__':
    main()
