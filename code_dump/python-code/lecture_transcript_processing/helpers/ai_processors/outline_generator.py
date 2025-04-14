import asyncio
import logging
import yaml
from pathlib import Path
from typing import Dict, List, Tuple

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
        tasks = []

        # First load any existing outlines that don't need refreshing
        for cleaned_file in cleaned_files:
            output_file = CACHE_DIRS['outlines'] / f'{cleaned_file.stem}.md'

            if not self.force_refresh and output_file.exists():
                logger.debug(f"Loading existing outline: {cleaned_file.stem}")
                outlines[cleaned_file.stem] = output_file.read_text()
                continue

            # Create task for files that need processing
            transcript_data = yaml.safe_load(cleaned_file.read_text())
            tasks.append(self._process_transcript(
                transcript=ProcessedTranscript(**transcript_data),
                file_stem=cleaned_file.stem
            ))

        # Process all remaining transcripts in parallel
        if tasks:
            CACHE_DIRS['outlines'].mkdir(exist_ok=True, parents=True)
            results = await asyncio.gather(*tasks)

            # Update outlines dictionary with results and save to files
            for file_stem, outline in results:
                outlines[file_stem] = outline
                output_file = CACHE_DIRS['outlines'] / f'{file_stem}.md'
                output_file.write_text(outline)

        return outlines

    async def _process_transcript(self, transcript: ProcessedTranscript, file_stem: str) -> Tuple[str, str]:
        """Process a transcript and return tuple of (file_stem, outline)"""
        outline = await self.generate_outline(transcript)
        return file_stem, outline

    async def generate_outline(self, transcript: ProcessedTranscript) -> str:
        """Generate an outline for a single transcript."""
        running_outline = f"# {transcript.title}\n"
        logger.info(f"Generating outline for: {transcript.title}")

        # Create tasks for all chunk processing
        tasks = []
        for i, chunk in enumerate(transcript.transcript_chunks):
            tasks.append(self._process_chunk(
                transcript=transcript,
                chunk=chunk,
                chunk_index=i,
                previous_outline=running_outline
            ))

        # Process chunks sequentially as each depends on previous result
        for task in tasks:
            running_outline = await task
            # Add a small delay to avoid hitting API rate limits
            await asyncio.sleep(0.5)

        return running_outline

    async def _process_chunk(self, transcript: ProcessedTranscript, chunk, chunk_index: int, previous_outline: str) -> str:
        """Process a single chunk of the transcript."""
        formatted_prompt = OUTLINE_SYSTEM_PROMPT.format(
            LECTURE_TITLE=transcript.title,
            CHUNK_NUMBER=chunk_index + 1,
            TOTAL_CHUNK_COUNT=len(transcript.transcript_chunks),
            PREVIOUS_OUTLINE=previous_outline,
            CURRENT_CHUNK=chunk.text
        )

        logger.debug(f"Processing outline chunk {chunk_index + 1}/{len(transcript.transcript_chunks)} for {transcript.title}")

        return await self.make_openai_text_request(
            system_prompt=formatted_prompt
        )