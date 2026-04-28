import re
from pathlib import Path

file_path = Path(r"g:\My Drive\Automation\prompts\batch_script_prompt.txt")
content = file_path.read_text(encoding="utf-8")

new_outro = "- Mandatory Outro: Every script MUST end with: \"மேலும் பல சிவில் இன்ஜினியரிங் தகவல்களுக்கு 'கிச்சா என்டர்பிரைசஸ்' (Kitcha Enterprises)-ஐ ஃபாலோ பண்ணுங்க! உங்கள் கட்டிட பணிகளுக்கு (Project) எங்களை உடனே தொடர்பு கொள்ளுங்க!\""

# Replace the line starting with - Mandatory Outro:
content = re.sub(r"- Mandatory Outro:.*", new_outro, content)

file_path.write_text(content, encoding="utf-8")
print("Successfully updated prompt template with correct encoding.")
