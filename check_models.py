"""Quick script to find available free models on OpenRouter."""
import requests

r = requests.get("https://openrouter.ai/api/v1/models")
data = r.json()
free_models = [m for m in data.get("data", []) if ":free" in m.get("id", "")]
for m in free_models[:20]:
    print(f"  {m['id']:60s}  ctx={m.get('context_length', '?')}")
print(f"\nTotal free models: {len(free_models)}")
