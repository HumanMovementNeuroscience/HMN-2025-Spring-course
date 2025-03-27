import asyncio
import logging
import os
from typing import Dict, List

from dotenv import load_dotenv

from .ai_processors.transcript_cleaner import TranscriptCleaner
from .ai_processors.outline_generator import OutlineGenerator
from .ai_processors.theme_synthesizer import ThemeSynthesizer

logger = logging.getLogger(__name__)
load_dotenv()

# Define key themes
KEY_THEMES = [
    "Human Perceptual Motor Neuroscience",
    "Philosophy of science, empiricism, and the scientific method",
    "AI",
    "Research Methodology",
    "Motion Capture",
    "Vision and eye movements",
    "Biomechanics, posture, and balance",
    "Teaching/personal philosophy",
    "Poster assignment"
]

class AITranscriptProcessor:
    """Orchestrates the entire transcript processing pipeline."""

    def __init__(self, force_refresh: bool = False):
        # Check for OpenAI API key
        if os.getenv('OPENAI_API_KEY') is None:
            raise ValueError("Please set OPENAI_API_KEY in your .env file")

        self.force_refresh = force_refresh
        self.models = {
            'cleanup': "gpt-4o-mini",
            'outline': "gpt-4o-mini",
            'synthesis': "gpt-4o-mini",
        }

        # Initialize processors
        self.cleaner = TranscriptCleaner(force_refresh=force_refresh, model=self.models['cleanup'])
        self.outline_generator = OutlineGenerator(force_refresh=force_refresh, model=self.models['outline'])
        self.theme_synthesizer = ThemeSynthesizer(
            force_refresh=force_refresh,
            model=self.models['synthesis'],
            themes=KEY_THEMES
        )

    async def process_transcripts(self):
        """Run the full transcript processing pipeline."""
        logger.info("Starting Transcript cleanup...")
        await self.cleaner.process_all_transcripts()

        logger.info("Generating video outlines...")
        await self.outline_generator.generate_all_outlines()

        logger.info("Synthesizing thematic outlines...")
        await self.theme_synthesizer.synthesize_themes()

        logger.info("Transcript processing complete!")