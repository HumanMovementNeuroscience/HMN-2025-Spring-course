"""
YouTube Lecture Processing Pipeline with Caching

Features:
- Automatic playlist processing with caching
- AI-powered transcript cleaning & analysis
- Thematic synthesis across lectures
- Dotenv configuration
- IDE-friendly with CLI override
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import List, Optional, Dict
from urllib.parse import parse_qs, urlparse

import requests
import yaml
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

# --- Configuration ---
load_dotenv()
if not os.getenv('OPENAI_API_KEY'):
    raise ValueError("Please set OPENAI_API_KEY in your .env file")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_PLAYLIST = "https://youtube.com/playlist?list=PLWxH2Ov17q5HDfMBJxD_cE1lowM1cr_BV"
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

CACHE_DIRS = {
    'raw': Path("lecture_transcripts/raw"),
    'cleaned': Path("lecture_transcripts/cleaned"),
    'outlines': Path("lecture_transcripts/outlines"),
    'themes': Path("lecture_transcripts/themes")
}

for directory in CACHE_DIRS.values():
    directory.mkdir(parents=True, exist_ok=True)

# --- Pydantic Models ---
class TranscriptEntry(BaseModel):
    text: str
    start: float
    dur: float
    end: Optional[float] = None

class VideoMetadata(BaseModel):
    title: str
    author: str
    viewCount: str
    description: str
    publish_date: str
    channel_id: str
    duration: str
    likeCount: Optional[str] = None
    tags: Optional[str] = None

class ProcessedTranscript(BaseModel):
    video_id: str = Field(..., title="YouTube video ID")
    title: str = Field(..., title="Video Title")
    transcript_chunks: List[TranscriptEntry] = Field(..., title="Transcript Chunks")
    full_transcript: str = Field(..., title="Full Transcript")

# --- Core Pipeline Components ---
class YouTubeProcessor:
    USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.83 Safari/537.36,gzip(gfe)'
    RE_YOUTUBE = re.compile(r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})', re.I)
    RE_XML_TRANSCRIPT = re.compile(r'<text start="([^"]*)" dur="([^"]*)">([^<]*)<\/text>')

    def __init__(self, force_refresh: bool = False):
        self.force_refresh = force_refresh

    def process_playlist(self, playlist_url: str = DEFAULT_PLAYLIST) -> List[str]:
        logger.info(f"Processing playlist: {playlist_url}")
        video_ids = self._get_playlist_videos(playlist_url)
        existing_videos = {f.stem for f in CACHE_DIRS['raw'].glob('*.yaml')}

        new_videos = [vid for vid in video_ids if vid not in existing_videos]
        if self.force_refresh:
            logger.info("Force refresh enabled - reprocessing all videos")
            new_videos = video_ids
        else:
            logger.info(f"Found {len(existing_videos)} cached videos, {len(new_videos)} new")

        for vid in new_videos:
            if video_data := self._process_video(vid):
                self._save_video_data(vid, video_data)

        return video_ids

    def _get_playlist_videos(self, playlist_url: str) -> List[str]:
        query = parse_qs(urlparse(playlist_url).query)
        if not (playlist_id := query.get('list', [None])[0]):
            raise ValueError("Invalid playlist URL")

        response = requests.get(
            f'https://www.youtube.com/playlist?list={playlist_id}',
            headers={'User-Agent': self.USER_AGENT}
        )
        response.raise_for_status()
        return list(set(re.findall(r'"videoId":"([^"]{11})"', response.text)))

    def _process_video(self, video_id: str) -> Optional[Dict]:
        try:
            logger.info(f"Processing video {video_id}")
            video_url = f'https://www.youtube.com/watch?v={video_id}'
            response = requests.get(video_url, headers={'User-Agent': self.USER_AGENT})
            response.raise_for_status()
            return self._extract_video_data(response.text, video_id)
        except Exception as e:
            logger.error(f"Failed to process {video_id}: {str(e)}")
            return None

    def _extract_video_data(self, html: str, video_id: str) -> Dict:
        metadata = {
            'title': self._extract_metadata(html, 'title'),
            'author': self._extract_metadata(html, 'author'),
            'viewCount': self._extract_metadata(html, 'viewCount'),
            'description': self._extract_metadata(html, 'shortDescription'),
            'publish_date': self._extract_metadata(html, 'publishDate'),
            'channel_id': self._extract_metadata(html, 'channelId'),
            'duration': self._extract_metadata(html, 'lengthSeconds'),
            'likeCount': self._extract_metadata(html, 'likeCount'),
            'tags': self._extract_metadata(html, 'keywords'),
        }
        return {
            'video_id': video_id,
            'metadata': VideoMetadata(**metadata),
            'transcript': self._get_transcript(html, video_id)
        }

    def _get_transcript(self, html: str, video_id: str) -> List[TranscriptEntry]:
        try:
            captions_json = html.split('"captions":')[1].split(',"videoDetails')[0]
            captions = json.loads(captions_json.replace('\n', ''))['playerCaptionsTracklistRenderer']
            transcript_url = captions['captionTracks'][0]['baseUrl']

            transcript_res = requests.get(transcript_url, headers={'User-Agent': self.USER_AGENT})
            transcript_res.raise_for_status()

            return [
                TranscriptEntry(text=text, start=float(start), dur=float(dur))
                for start, dur, text in self.RE_XML_TRANSCRIPT.findall(transcript_res.text)
            ]
        except Exception as e:
            logger.error(f"Transcript error for {video_id}: {str(e)}")
            return []

    def _save_video_data(self, video_id: str, data: Dict):
        output_path = CACHE_DIRS['raw'] / f'{video_id}.yaml'
        with open(output_path, 'w') as f:
            yaml.dump(data, f)
        logger.debug(f"Saved raw data for {video_id}")

    @staticmethod
    def _extract_metadata(html: str, key: str) -> str:
        match = re.search(f'"{key}":"(.*?)"', html)
        return match.group(1) if match else ''

class AITranscriptProcessor:
    def __init__(self, force_refresh: bool = False):
        self.force_refresh = force_refresh
        self.client = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.models = {
            'cleanup': "gpt-4-0125-preview",
            'outline': "gpt-4o",
            'synthesis': "gpt-4-turbo-preview"
        }

    async def process_transcripts(self):
        await self._clean_transcripts()
        await self._generate_outlines()
        await self._synthesize_themes()

    async def _clean_transcripts(self):
        logger.info("Starting transcript cleaning")
        raw_files = list(CACHE_DIRS['raw'].glob('*.yaml'))

        for raw_file in raw_files:
            output_file = CACHE_DIRS['cleaned'] / raw_file.name
            if not self.force_refresh and output_file.exists():
                logger.debug(f"Skipping existing cleaned transcript: {raw_file.stem}")
                continue

            video_data = yaml.safe_load(raw_file.read_text())
            processed = await self._clean_single(video_data)
            with open(output_file, 'w') as f:
                yaml.dump(processed.model_dump(), f)

    async def _clean_single(self, video_data: Dict) -> ProcessedTranscript:
        system_prompt = (
            "Clean spoken text into grammatically correct form. Remove filler words. "
            "Maintain original meaning. Use correct punctuation and capitalization."
        )

        async def cleanup_chunk(chunk: TranscriptEntry):
            return await self._ai_request(
                system_prompt=system_prompt,
                input_data=chunk.model_dump(),
                output_model=TranscriptEntry,
                model_type='cleanup'
            )

        chunks = await asyncio.gather(*[
            cleanup_chunk(TranscriptEntry(**c)) for c in video_data['transcript']
        ])

        return ProcessedTranscript(
            video_id=video_data['video_id'],
            title=video_data['metadata'].title,
            transcript_chunks=chunks,
            full_transcript=" ".join([c.text for c in chunks])
        )

    async def _generate_outlines(self):
        logger.info("Generating lecture outlines")
        cleaned_files = list(CACHE_DIRS['cleaned'].glob('*.yaml'))

        for cleaned_file in cleaned_files:
            output_file = CACHE_DIRS['outlines'] / f'{cleaned_file.stem}.md'
            if not self.force_refresh and output_file.exists():
                logger.debug(f"Skipping existing outline: {cleaned_file.stem}")
                continue

            transcript = yaml.safe_load(cleaned_file.read_text())
            outline = await self._outline_single(transcript)
            output_file.write_text(outline)

    async def _outline_single(self, transcript: Dict) -> str:
        base_prompt = """
        Generate markdown outline from lecture content. Focus on scientific content.
        Use H1-H3 headers. Remove administrative fluff. Be specific and detailed.
        """
        running_outline = f"# {transcript['title']}\n"

        for chunk in transcript['transcript_chunks']:
            prompt = f"Current Outline:\n{running_outline}\nNew Content:\n{chunk['text']}"
            running_outline = await self._ai_request(
                system_prompt=base_prompt,
                input_data=prompt,
                output_model=str,
                model_type='outline'
            )
            await asyncio.sleep(1)  # Rate limiting

        return running_outline

    async def _synthesize_themes(self):
        logger.info("Synthesizing thematic outlines")
        outline_files = list(CACHE_DIRS['outlines'].glob('*.md'))
        combined_outlines = "\n\n".join(f.read_text() for f in outline_files)
        outline_hash = hashlib.md5(combined_outlines.encode()).hexdigest()

        hash_file = CACHE_DIRS['themes'] / '.version'
        if not self.force_refresh and hash_file.exists():
            if hash_file.read_text() == outline_hash:
                logger.info("Themes up-to-date - skipping regeneration")
                return

        tasks = [self._process_theme(combined_outlines, theme) for theme in KEY_THEMES]
        theme_results = await asyncio.gather(*tasks)

        for theme, content in zip(KEY_THEMES, theme_results):
            clean_name = theme.replace(" ", "_").replace("/", "_")
            (CACHE_DIRS['themes']/f'{clean_name}.md').write_text(content)

        hash_file.write_text(outline_hash)

    async def _process_theme(self, outlines: str, theme: str) -> str:
        prompt = f"""
        Generate comprehensive outline for theme: {theme}
        Use H1 headers and detailed bullets. Focus on specific content from lectures.
        Include direct quotes and key concepts. Avoid vague statements.
        """
        return await self._ai_request(
            system_prompt=prompt,
            input_data=outlines,
            output_model=str,
            model_type='synthesis'
        )

    async def _ai_request(self, system_prompt: str, input_data, output_model, model_type: str):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(input_data)}
        ]

        response = await self.client.chat.completions.create(
            model=self.models[model_type],
            messages=messages,
            temperature=0.0,
            response_format={"type": "json_object"} if output_model != str else None
        )

        if issubclass(output_model, BaseModel):
            return output_model(**json.loads(response.choices[0].message.content))
        return response.choices[0].message.content

# --- Main Execution ---
async def main(playlist_url: str = DEFAULT_PLAYLIST, force_refresh: bool = False):
    try:
        logger.info("Starting YouTube lecture processing pipeline")

        # Stage 1: YouTube Data Collection
        yt_processor = YouTubeProcessor(force_refresh=force_refresh)
        video_ids = yt_processor.process_playlist(playlist_url)


        # Stage 2: AI Processing
        ai_processor = AITranscriptProcessor(force_refresh=force_refresh)
        await ai_processor.process_transcripts()

        logger.info("Pipeline completed successfully")
    except Exception as e:
        logger.error(f"Pipeline failed: {str(e)}")
        raise

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process YouTube lecture playlist")
    parser.add_argument("--playlist", type=str, default=DEFAULT_PLAYLIST, help="YouTube playlist URL")
    parser.add_argument("--force", action="store_true", help="Force reprocess all data")
    args = parser.parse_args()

    asyncio.run(main(args.playlist, args.force))