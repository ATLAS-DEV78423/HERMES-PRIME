from __future__ import annotations

from typing import Any


def text_to_speech(text: str, voice: str = "en-US-JennyNeural") -> str:
    """Convert text to speech using edge-tts."""
    try:
        import edge_tts
        import asyncio

        async def _tts() -> str:
            output_file = "/tmp/hermes_tts.mp3"
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output_file)
            return f"Speech saved to {output_file}"

        return asyncio.run(_tts())
    except ImportError:
        return "TTS not available. Install: pip install edge-tts"
    except Exception as e:
        return f"TTS error: {e}"


def get_tts_schema() -> dict[str, Any]:
    return {
        "name": "text_to_speech",
        "description": "Convert text to spoken audio",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to speak"},
                "voice": {"type": "string", "description": "Voice to use", "default": "en-US-JennyNeural"},
            },
            "required": ["text"],
        },
    }


__all__ = ["text_to_speech", "get_tts_schema"]
