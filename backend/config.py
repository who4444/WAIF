from dotenv import load_dotenv
import os

load_dotenv()

def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

def _csv_env(name: str, default: str) -> list[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_LLM_MODEL = os.getenv("OPENROUTER_LLM_MODEL","google/gemma-4-31b-it:free")
OPENROUTER_EMBEDDING_MODEL = os.getenv("OPENROUTER_EMBEDDING_MODEL","nvidia/llama-nemotron-embed-vl-1b-v2:free")
FISHSPEECH_REFERENCE_DIR = os.getenv("FISHSPEECH_REFERENCE_DIR", "backend/static/voice_references")
FISHSPEECH_SERVER_URL = os.getenv("FISHSPEECH_SERVER_URL", "https://modal.com/apps/who4444/main")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
MODAL_ENABLED = _bool_env("MODAL_ENABLED", True)
MODAL_TOKEN = os.getenv("MODAL_TOKEN", "")
GITHUB_TOKEN=  os.getenv("GITHUB_TOKEN", "")    
WS_PORT = int(os.getenv("WS_PORT", "8000"))
WAIF_API_KEY = os.getenv("WAIF_API_KEY", "")
WAIF_ALLOWED_ORIGINS = _csv_env(
    "WAIF_ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
)
