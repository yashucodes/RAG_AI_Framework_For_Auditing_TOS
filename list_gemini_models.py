# list_gemini_models.py
#
# Purpose: Show every Gemini model this API key can actually use, with
# clear messages if something's wrong, so we fix the KEY first before
# touching app.py again.

from dotenv import load_dotenv
from google import genai
import os

load_dotenv()

api_key = os.environ.get("GEMINI_API_KEY")

if not api_key:
    print("PROBLEM: No GEMINI_API_KEY was found.")
    print("Check that:")
    print("  1. You have a file named exactly '.env' (not '.env.txt')")
    print("  2. It's in the SAME folder you're running this script from")
    print("  3. It has a line like: GEMINI_API_KEY=your_real_key_here")
else:
    print(f"Found a key. It ends in: ...{api_key[-4:]}\n")

    client = genai.Client(api_key=api_key)

    print("Asking Google which models this key can use...\n")
    found_any = False
    try:
        for model in client.models.list():
            found_any = True
            print(model)
            print("-" * 60)
    except Exception as e:
        print(f"PROBLEM: The request itself failed with this error:\n{e}")
        found_any = True  # don't also print the "no models" message below

    if not found_any:
        print("PROBLEM: This key can't see ANY models.")
        print("This usually means you copied a SHORTENED key (like '...kAFQ')")
        print("instead of the full key. Go back to https://aistudio.google.com/apikey,")
        print("click directly on the key row to copy the FULL key, and paste")
        print("that whole thing into your .env file.")