import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Dict, List

from .base_processor import BaseProcessor
from ..cache_stuff import CACHE_DIRS
from ..yt_prompts import THEME_SYNTHESIS_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

class ThemeSynthesizer(BaseProcessor):
    """Responsible for synthesizing themes across lecture outlines."""

    def __init__(self, force_refresh: bool = False, model: str = "gpt-4o-mini", themes: List[str] = None):
        super().__init__(force_refresh, model)
        self.themes = themes or []

    async def synthesize_themes(self) -> Dict[str, str]:
        """Generate thematic synthesis across all lecture outlines."""
        logger.info("Synthesizing thematic outlines")
        outline_files = list(CACHE_DIRS['outlines'].glob('*.md'))
        theme_results = {}

        if not outline_files:
            logger.warning("No outline files found to synthesize themes")
            return theme_results

        combined_outlines = "\n\n".join(f.read_text() for f in outline_files)
        outline_hash = hashlib.md5(combined_outlines.encode()).hexdigest()

        hash_file = CACHE_DIRS['themes'] / '.version'
        if not self.force_refresh and hash_file.exists():
            if hash_file.read_text() == outline_hash:
                logger.info("Themes up-to-date - loading from cache")
                for theme in self.themes:
                    clean_name = self._clean_theme_name(theme)
                    theme_file = CACHE_DIRS['themes'] / f'{clean_name}.md'
                    if theme_file.exists():
                        theme_results[theme] = theme_file.read_text()
                return theme_results

        tasks = [self._process_theme(combined_outlines, theme) for theme in self.themes]
        theme_contents = await asyncio.gather(*tasks)

        CACHE_DIRS['themes'].mkdir(exist_ok=True, parents=True)
        for theme, content in zip(self.themes, theme_contents):
            clean_name = self._clean_theme_name(theme)
            theme_file = CACHE_DIRS['themes'] / f'{clean_name}.md'
            theme_file.write_text(content)
            theme_results[theme] = content

        hash_file.write_text(outline_hash)
        return theme_results

    async def _process_theme(self, outlines: str, theme: str) -> str:
        """Process a specific theme across all lecture outlines."""
        logger.info(f"Processing theme: {theme}")
        formatted_prompt = THEME_SYNTHESIS_SYSTEM_PROMPT.format(
            theme=theme,
            all_themes=", ".join(t for t in self.themes if t != theme),
            lecture_outlines=outlines
        )

        return await self.make_openai_text_request(system_prompt=formatted_prompt)

    def _clean_theme_name(self, theme: str) -> str:
        """Convert theme name to a safe filename."""
        return theme.replace(" ", "_").replace("/", "_")