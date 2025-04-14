import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional, Type, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)

class BaseProcessor:
    """Base class for AI processors with common functionality."""

    def __init__(self, force_refresh: bool = False, model: str = "gpt-4o-mini"):
        self.force_refresh = force_refresh
        self.client = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'), timeout=600)
        self.model = model

    async def make_openai_json_mode_ai_request(self,
                                               system_prompt: str,
                                               input_data: dict,
                                               output_model: Type[T]) -> T:
        """Make an OpenAI request with JSON mode for structured output."""
        messages = [{"role": "system", "content": system_prompt}]
        if input_data:
            messages.append({"role": "user", "content": json.dumps(input_data)})

        try:
            # Use the parse method with the Pydantic model directly
            response = await self.client.beta.chat.completions.parse(
                model=self.model,
                messages=messages,
                response_format=output_model,
            )

            # The parse method returns the parsed model directly
            return response.choices[0].message.parsed
        except Exception as e:
            logger.error(f"Error in OpenAI JSON request: {e}")
            raise

    async def make_openai_text_request(self, system_prompt: str) -> str:
        """Make an OpenAI request for text generation."""
        messages = [{"role": "system", "content": system_prompt}]

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.0,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error in OpenAI text request: {e}")
            raise