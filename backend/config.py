import os
from dotenv import load_dotenv

# Load local environment variables from .env
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def get_gemini_client(api_key: str = None):
    """
    Initializes and returns the Google GenAI Client.
    Supports dynamic API key injection from UI or fallback to environment.
    """
    from google import genai
    
    # Precedence: Explicit passed key > Environment GEMINI_API_KEY > Environment GOOGLE_API_KEY
    key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    
    if not key:
        raise ValueError(
            "GEMINI_API_KEY is missing. Please set it in your environment, "
            "write it to backend/.env, or enter it in the dashboard settings."
        )
    return genai.Client(api_key=key)
