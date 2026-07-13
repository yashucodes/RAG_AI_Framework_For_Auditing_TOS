# check_gemini_model.py
#
# Purpose: app.py needs a model that supports plain text generation
# (the "generateContent" action) -- NOT the live-audio/streaming models
# ("bidiGenerateContent") that showed up in the raw list. This script
# filters down to only the usable ones and tells you directly whether
# 'gemini-2.5-flash' (what app.py currently uses) is one of them.

from dotenv import load_dotenv
from google import genai
import os

load_dotenv()

api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

TARGET_MODEL = "gemini-2.5-flash"

print("Models that support plain text generation (generateContent):\n")

usable_models = []
for model in client.models.list():
    actions = getattr(model, "supported_actions", None) or []
    if "generateContent" in actions:
        usable_models.append(model.name)
        print(f"  - {model.name}")

if not usable_models:
    print("  (none found)")

print()

target_found = any(TARGET_MODEL in name for name in usable_models)

if target_found:
    print(f"GOOD NEWS: '{TARGET_MODEL}' is available and supports generateContent.")
    print("app.py should work as-is -- no changes needed. Try test_gemini_pipeline.py next.")
elif usable_models:
    suggestion = usable_models[0].replace("models/", "")
    print(f"'{TARGET_MODEL}' was NOT in the usable list above.")
    print(f"Open app.py and change this line:")
    print(f'    GEMINI_MODEL = "{TARGET_MODEL}"')
    print(f"to:")
    print(f'    GEMINI_MODEL = "{suggestion}"')
else:
    print("No models support generateContent at all for this key.")
    print("That means this key's project doesn't have the right API turned on.")
    print("Try the other key (Default Gemini Project, ...t6uw) instead.")