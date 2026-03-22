from openai import AsyncOpenAI
from dotenv import load_dotenv
import os
import json
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
load_dotenv()

class WAIF_response(BaseModel):
    state: str = Field(description="")
    dialog: str = Field(description="")
    thought: str = Field(description="")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(description="")

class LLMClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = AsyncOpenAI(api_key=self.api_key, 
                                  base_url=os.getenv("OPENAI_API_BASE_URL", "https://api.openai.com/v1"))
    