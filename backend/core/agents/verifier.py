import json
import re
from typing import Any
from core.llm_client import llm_complete
from .control_schema import VerificationResult

VERIFIER_SYSTEM = """You are Leiwen's verifier.
Review subagent results before the final response.

Check:
- Did each task satisfy its success criteria?
- Are there missing requirements?
- Are there unsupported claims?
- Are there contradictions between subagent outputs?
- Are safety limits respected?
- What should the final response mention or avoid?

Return JSON only:
{
  "status": "pass" | "revise" | "fail",
  "issues": [],
  "missing_requirements": [],
  "confidence": 0.0,
  "final_response_guidance": ""
}
"""

def _extract_json(text: str) -> dict[str,Any]:
    stripped = text.strip()
    fenced = re.search(r"```json\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()
    else:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end != -1 and end > start:
            stripped = stripped[start:end+1].strip()
    return json.loads(stripped)

async def verify_result(
    original_request: str,
    plan: dict,
    results: list[dict],
) -> VerificationResult:
    messages = [{
        "role": "user",
        "content": (
            f"Original user request: {original_request}\n\n"
            f"Plan:\n{json.dumps(plan, indent=2)}\n\n"
            f"Task results:\n{json.dumps(results, indent=2)}\n\n"
        ),
    }]

    raw_response = await llm_complete(
        messages=messages,
        system=VERIFIER_SYSTEM,
        mode="reasoning",
        max_tokens=512,
    )
    try:
        response = _extract_json(raw_response)
    except Exception as e:
        print(f"Error parsing verifier response: {e}")
        return {
            "status": "revise",
            "issues": ["Failed to parse verifier response."],
            "missing_requirements": [],
            "confidence": 0.1,
            "final_response_guidance": "Be cautious and mention the uncertainty in the final response." 
        }
    return {
        "status": response.get("status", "revise"),
        "issues": response.get("issues", []),
        "missing_requirements": response.get("missing_requirements", []),
        "confidence": response.get("confidence", 0.0),
        "final_response_guidance": response.get("final_response_guidance", ""),
    }   
