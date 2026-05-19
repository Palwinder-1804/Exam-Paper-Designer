import os
import requests
from fastapi import HTTPException

class HFResponse:
    def __init__(self, content: str):
        self.content = content

class HuggingFaceLLM:
    def __init__(self, model: str, temperature: float = 0.35, format: str = None, **kwargs):
        self.model = model
        self.temperature = temperature
        self.format = format
        
    def invoke(self, prompt: str) -> HFResponse:
        token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACEHUB_API_TOKEN")
        if not token or token.strip() == "" or token == "your_huggingface_token_here":
            raise HTTPException(
                status_code=400,
                detail=(
                    "Hugging Face API token is missing. Please set HF_TOKEN in your "
                    ".env file or environment variables. You can get a free token from "
                    "https://huggingface.co/settings/tokens"
                )
            )
            
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token.strip()}"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": self.temperature,
            "max_tokens": 1500
        }
        
        if self.format == "json":
            payload["response_format"] = {"type": "json_object"}
            
        url = "https://router.huggingface.co/v1/chat/completions"
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            
            if response.status_code == 401:
                raise HTTPException(
                    status_code=401,
                    detail="Hugging Face API token is invalid or unauthorized. Please check your HF_TOKEN."
                )
            elif response.status_code == 429:
                raise HTTPException(
                    status_code=429,
                    detail="Hugging Face Inference API rate limit reached. Please try again in a few moments."
                )
            elif response.status_code != 200:
                # Try fallback without response_format if it was a json mode failure
                if self.format == "json" and "response_format" in payload:
                    fallback_payload = payload.copy()
                    fallback_payload.pop("response_format")
                    try:
                        fallback_resp = requests.post(url, headers=headers, json=fallback_payload, timeout=60)
                        if fallback_resp.status_code == 200:
                            res_data = fallback_resp.json()
                            content = res_data["choices"][0]["message"]["content"]
                            return HFResponse(content)
                    except Exception:
                        pass
                
                # If fallback failed or wasn't applicable
                try:
                    error_detail = response.json()
                    if isinstance(error_detail, dict):
                        error_detail = error_detail.get("error", response.text)
                except Exception:
                    error_detail = response.text
                
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Hugging Face API Error ({response.status_code}): {error_detail}"
                )
                
            res_data = response.json()
            content = res_data["choices"][0]["message"]["content"]
            return HFResponse(content)
            
        except requests.RequestException as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to communicate with Hugging Face API: {str(e)}"
            )
