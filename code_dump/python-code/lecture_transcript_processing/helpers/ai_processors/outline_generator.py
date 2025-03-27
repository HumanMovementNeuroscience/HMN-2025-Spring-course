import asyncio
import logging
import yaml
from pathlib import Path
from typing import Dict, List

from .base_processor import BaseProcessor
from ..cache_stuff import CACHE_DIRS
from ..yt_models import ProcessedTranscript
from ..yt_prompts import OUTLINE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

class OutlineGenerator(BaseProcessor):
    """Responsible for generating lecture outlines from cleaned transcripts."""

    async def generate_all_outlines(self) -> Dict[str, str]:
        """Generate outlines for all cleaned transcripts."""
        logger.info("Generating lecture outlines")
        cleaned_files = list(CACHE_DIRS['cleaned'].glob('*.yaml'))
        outlines = {}

        for cleaned_file in cleaned_files:
            output_file = CACHE_DIRS['outlines'] / f'{cleaned_file.stem}.md'

            if not self.force_refresh and output_file.exists():
                logger.debug(f"Loading existing outline: {cleaned_file.stem}")
                outlines[cleaned_file.stem] = output_file.read_text()
                continue

            transcript_data = yaml.safe_load(cleaned_file.read_text())
            outline = await self.generate_outline(ProcessedTranscript(**transcript_data))
            outlines[cleaned_file.stem] = outline

            CACHE_DIRS['outlines'].mkdir(exist_ok=True, parents=True)
            output_file.write_text(outline)

        return outlines

    async def generate_outline(self, transcript: ProcessedTranscript) -> str:
        """Generate an outline for a single transcript."""
        running_outline = f"# {transcript.title}\n"
        logger.info(f"Generating outline for: {transcript.title}")

        for i, chunk in enumerate(transcript.transcript_chunks):
            formatted_prompt = OUTLINE_SYSTEM_PROMPT.format(
                LECTURE_TITLE=transcript.title,
                CHUNK_NUMBER=i + 1,
                TOTAL_CHUNK_COUNT=len(transcript.transcript_chunks),
                PREVIOUS_OUTLINE=running_outline,
                CURRENT_CHUNK=chunk.text
            )

            logger.debug(f"Processing outline chunk {i + 1}/{len(transcript.transcript_chunks)} for {transcript.title}")

            running_outline = await self.make_openai_text_request(
                system_prompt=formatted_prompt
            )

            # Rate limiting to avoid hitting API limits
            await asyncio.sleep(1)

        return running_outline