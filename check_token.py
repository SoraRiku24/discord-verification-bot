from dotenv import load_dotenv
import os

load_dotenv()
tok = os.getenv("DISCORD_TOKEN", "")
print("Loaded token length:", len(tok))
print("Starts with:", tok[:5])
