import os
import logging

class TokenRedactFilter(logging.Filter):
    """Replace sensitive tokens in log messages with [REDACTED]."""
    def __init__(self, tokens: list[str]):
        super().__init__()
        # Filter out empty or short tokens to prevent accidental redaction of short strings
        self._tokens = [t for t in tokens if t and len(t) > 5]

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._tokens:
            return True
            
        # Get the formatted message to check for tokens
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
            
        found = False
        for token in self._tokens:
            if token in msg:
                msg = msg.replace(token, "bot[REDACTED]")
                found = True
                
        if found:
            # Override record.msg with the fully formatted and redacted message
            # and clear record.args to prevent double-formatting or exceptions
            record.msg = msg
            record.args = ()
            
        return True

def apply_security_filters():
    """Apply the token redaction filter to root, specific loggers, and all active handlers."""
    try:
        from core.config import settings
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "") or settings.TELEGRAM_BOT_TOKEN
        if not token:
            return
            
        redact_filter = TokenRedactFilter([token])
        
        # 1. Apply to the root logger
        root_logger = logging.getLogger()
        root_logger.addFilter(redact_filter)
        
        # 2. Apply to all active handlers on the root logger
        for handler in root_logger.handlers:
            handler.addFilter(redact_filter)
            
        # 3. Apply to specific known loggers and their handlers
        loggers_to_patch = ["httpx", "telegram", "KaggleBot", "bot.main", "bot.handlers", "core.orchestrator"]
        for name in loggers_to_patch:
            l = logging.getLogger(name)
            l.addFilter(redact_filter)
            for h in l.handlers:
                h.addFilter(redact_filter)
                
    except Exception:
        pass
