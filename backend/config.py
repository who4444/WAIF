from dotenv import load_dotenv
import os

load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
FISHSPEECH_REFERENCE_DIR = os.getenv("FISHSPEECH_REFERENCE_DIR", "backend/static/voice_references")
FISHSPEECH_SERVER_URL = os.getenv("FISHSPEECH_SERVER_URL", "https://modal.com/apps/who4444/main")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
MODAL_ENABLED = os.getenv("MODAL_ENABLED", "true")
MODAL_TOKEN = os.getenv("MODAL_TOKEN", "")
GITHUB_TOKEN=  os.getenv("GITHUB_TOKEN", "")    
WS_PORT = int(os.getenv("WS_PORT", "8000"))