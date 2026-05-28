from __future__ import annotations

from typing import Any


def vision_analyze(image_url: str, prompt: str = "Describe this image") -> str:
    """Analyze an image using vision-capable LLM."""
    try:
        from ollama import Client

        client = Client()
        response = client.generate(
            model="llava",
            prompt=prompt,
            images=[image_url],
        )
        return response.get("response", "No response from vision model")
    except ImportError:
        return "Vision not available. Install: pip install ollama"
    except Exception as e:
        return f"Vision error: {e}"


def get_vision_schema() -> dict[str, Any]:
    return {
        "name": "vision_analyze",
        "description": "Analyze an image using vision-capable AI",
        "parameters": {
            "type": "object",
            "properties": {
                "image_url": {"type": "string", "description": "URL or path to image"},
                "prompt": {"type": "string", "description": "Analysis prompt", "default": "Describe this image"},
            },
            "required": ["image_url"],
        },
    }


__all__ = ["vision_analyze", "get_vision_schema"]
