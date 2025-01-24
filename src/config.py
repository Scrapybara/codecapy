import os
from dotenv import load_dotenv

load_dotenv()

GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")
GITHUB_APP_ID = os.getenv("GITHUB_APP_ID")
GITHUB_PRIVATE_KEY_PATH = os.getenv("GITHUB_PRIVATE_KEY_PATH")
SCRAPYBARA_API_KEY = os.getenv("SCRAPYBARA_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
