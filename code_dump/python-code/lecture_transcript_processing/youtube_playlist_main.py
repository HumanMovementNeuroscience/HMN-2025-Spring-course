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
from typing import List, Optional, Dict, Type
from urllib.parse import parse_qs, urlparse

import requests
import yaml
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel, Field


# --- Configuration ---
load_dotenv()
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if OPENAI_API_KEY is None:
    raise ValueError("Please set OPENAI_API_KEY in your .env file")
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_PLAYLIST = "https://youtube.com/playlist?list=PLWxH2Ov17q5HDfMBJxD_cE1lowM1cr_BV"
CLEANUP_TRANSCRIPT_SYSTEM_PROMPT = """    
        Clean up the spoken text in the following transcript into a more grammatically correct form.
        Remove filler words likes um, ah, etc and make the output use correct punctuation and 
        capitalization

        The goal is to produce a version of the spoken lecture that makes sense when written down, but which matches 
        the meaning of the original text as closely as possible
        
        YOU MUST MAINTAIN THE ORIGINAL MEANING AND INTENTION AND INCLUDE ALLL CONTENT!
        DO NOT MAKE THINGS UP! DO NOT ATTEMPT TO ADD ADDITIONAL MEANING TO THE SPOKEN 
        TEXT!

"""
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
    'raw': Path(__file__).parent / "lecture_transcripts/raw",
    'cleaned': Path(__file__).parent / "lecture_transcripts/cleaned",
    'outlines': Path(__file__).parent / "lecture_transcripts/outlines",
    'themes': Path(__file__).parent / "lecture_transcripts/themes"
}


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

    @property
    def clean_title(self) -> str:
        return re.sub(r'[^a-zA-Z0-9 ]', '', self.title).replace(' ', '_').lower()

class VideoTranscriptData(BaseModel):
    video_id: str
    metadata:  VideoMetadata
    transcript:   List[TranscriptEntry]

    @property
    def key_name(self) -> str:
        return f"{self.metadata.clean_title}_{self.video_id}"

class ProcessedTranscript(BaseModel):
    video_id: str = Field(..., title="YouTube video ID")
    title: str = Field(..., title="Video Title")
    transcript_chunks: List[TranscriptEntry] = Field(..., title="Transcript Chunks")
    full_transcript: str = Field(..., title="Full Transcript")


# --- Core Pipeline Components ---
class YouTubePlaylistExtractor(BaseModel):
    USER_AGENT: str = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.83 Safari/537.36,gzip(gfe)'
    RE_YOUTUBE: str = re.compile(
        r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})', re.I)
    RE_XML_TRANSCRIPT: str = re.compile(r'<text start="([^"]*)" dur="([^"]*)">([^<]*)<\/text>')
    force_refresh: bool = Field(default=False, title="Force reprocess all data")

    def extract_raw_playlist_data(self, playlist_url: str = DEFAULT_PLAYLIST) -> dict[str, VideoTranscriptData]:
        logger.info(f"Processing playlist: {playlist_url}")
        video_ids = self._get_playlist_videos(playlist_url)
        existing_videos = {f.stem for f in Path(CACHE_DIRS['raw']).glob('*.yaml')}

        new_videos = [vid for vid in video_ids if vid not in existing_videos]
        if self.force_refresh:
            logger.info("Force refresh enabled - reprocessing all videos")
            new_videos = video_ids
        else:
            logger.info(f"Found {len(existing_videos)} cached videos, {len(new_videos)} new")
        video_data_by_video = {}
        for vid in new_videos:
            video_data =  self.get_video_transcript_data(vid)
            video_data_by_video[video_data.key_name] = video_data
        return video_data_by_video

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

    def get_video_transcript_data(self, video_id: str) -> VideoTranscriptData:
        try:
            video_url = f'https://www.youtube.com/watch?v={video_id}'
            logger.info(f"Requesting video data for {video_id} from {video_url}")
            response = requests.get(video_url, headers={'User-Agent': self.USER_AGENT})
            response.raise_for_status()
            logger.debug(f"Received response for {video_id} - length: ~{len(response.text.split(' '))} words")
            return self._extract_video_data(response.text, video_id)
        except Exception as e:
            logger.error(f"Failed to process {video_id}: {str(e)}")
            raise

    def _extract_video_data(self, video_html: str, video_id: str) -> VideoTranscriptData:
        return VideoTranscriptData(
            video_id =  video_id,
            metadata =  VideoMetadata(
                title=self._extract_metadata(video_html, 'title'),
                author=self._extract_metadata(video_html, 'author'),
                viewCount=self._extract_metadata(video_html, 'viewCount'),
                description=self._extract_metadata(video_html, 'shortDescription'),
                publish_date=self._extract_metadata(video_html, 'publishDate'),
                channel_id=self._extract_metadata(video_html, 'channelId'),
                duration=self._extract_metadata(video_html, 'lengthSeconds'),
                likeCount=self._extract_metadata(video_html, 'likeCount'),
                tags=self._extract_metadata(video_html, 'keywords'), ),
            transcript =  self._get_transcript(video_html, video_id)
        )

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

    def _save_video_data(self, video_id: str, data: VideoTranscriptData):
        output_path = Path(CACHE_DIRS['raw']) / f'{data.key_name}.yaml'
        Path(CACHE_DIRS['raw']).mkdir(exist_ok=True, parents=True)
        with open(output_path, 'w') as f:
            yaml.dump(data.model_dump(), f)
        logger.debug(f"Saved raw data for {video_id}")

    @staticmethod
    def _extract_metadata(html: str, key: str) -> str:
        match = re.search(f'"{key}":"(.*?)"', html)
        return match.group(1) if match else ''


class AITranscriptProcessor:
    def __init__(self, force_refresh: bool = False):
        self.force_refresh = force_refresh
        self.client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        self.models = {
            'cleanup': "gpt-4o-mini",
            'outline': "gpt-4o",
            'synthesis': "gpt-4o"
        }

    async def process_transcripts(self):
        logger.info("Starting Transcript cleanup...")
        await self._clean_transcripts()
        logger.info("Generating video outlines...")
        await self._generate_outlines()
        logger.info("Synthesizing thematic outlines...")
        await self._synthesize_themes()

    async def _clean_transcripts(self):
        logger.info("Starting transcript cleaning")
        raw_files = list(Path(CACHE_DIRS['raw']).glob('*.yaml'))

        for raw_file in raw_files:
            output_file = Path(CACHE_DIRS['cleaned'] )/ raw_file.name
            if not self.force_refresh and output_file.exists():
                logger.debug(f"Skipping existing cleaned transcript: {raw_file.stem}")
                continue

            video_data = VideoTranscriptData(**yaml.safe_load(raw_file.read_text()))
            processed = await self._clean_single(video_data)
            with open(output_file, 'w') as f:
                yaml.dump(processed.model_dump(), f)

    async def _clean_single(self, video_data: VideoTranscriptData) -> ProcessedTranscript:
        system_prompt = (
            "Clean spoken text into grammatically correct form. Remove filler words. "
            "Maintain original meaning. Use correct punctuation and capitalization."
        )

        async def cleanup_chunk(chunk: TranscriptEntry):
            return await self.make_openai_json_mode_ai_request(
                system_prompt=system_prompt,
                input_data=chunk.model_dump(),
                output_model=TranscriptEntry,
                model_type='cleanup'
            )

        chunks = await asyncio.gather(*[
            cleanup_chunk(transcript_chunk) for transcript_chunk in video_data.transcript
        ])

        return ProcessedTranscript(
            video_id=video_data['video_id'],
            title=video_data['metadata'].title,
            transcript_chunks=chunks,
            full_transcript=" ".join([c.text for c in chunks])
        )

    async def _generate_outlines(self):
        logger.info("Generating lecture outlines")
        cleaned_files = list(Path(CACHE_DIRS['cleaned']).glob('*.yaml'))

        for cleaned_file in cleaned_files:
            output_file = Path(CACHE_DIRS['outlines']) / f'{cleaned_file.stem}.md'
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
        outline_files = list((Path(CACHE_DIRS['outlines'])).glob('*.md'))
        combined_outlines = "\n\n".join(f.read_text() for f in outline_files)
        outline_hash = hashlib.md5(combined_outlines.encode()).hexdigest()

        hash_file = Path(CACHE_DIRS['themes'] )/ '.version'
        if not self.force_refresh and hash_file.exists():
            if hash_file.read_text() == outline_hash:
                logger.info("Themes up-to-date - skipping regeneration")
                return

        tasks = [self._process_theme(combined_outlines, theme) for theme in KEY_THEMES]
        theme_results = await asyncio.gather(*tasks)
        Path(CACHE_DIRS['themes']).mkdir(exist_ok=True,parents=True)
        for theme, content in zip(KEY_THEMES, theme_results):
            clean_name = theme.replace(" ", "_").replace("/", "_")
            (Path(CACHE_DIRS['themes']) / f'{clean_name}.md').write_text(content)

        hash_file.write_text(outline_hash)

    async def _process_theme(self, outlines: str, theme: str) -> str:
        prompt = f"""
        Generate comprehensive outline for theme: {theme}
        Use H1 headers and detailed bullets. Focus on specific content from lectures.
        Include direct quotes and key concepts. Avoid vague statements.
        """
        return await self.make_openai_json_mode_ai_request(
            system_prompt=prompt,
            input_data=outlines,
            output_model=str,
            model_type='synthesis'
        )

    async def make_openai_json_mode_ai_request(self,
                                               system_prompt: str,
                                               prompt_model: Type[BaseModel],
                                               llm_model: str,
                                               user_input: str | None = None,
                                               results_list: list | None = None):
        messages = [{"role": "system", "content": system_prompt}]
        if user_input is not None:
            messages.append({"role": "user", "content": user_input})
        response = await self.client.beta.chat.completions.parse(
            model=llm_model,
            messages=messages,
            response_format=prompt_model
        )
        output = prompt_model(**json.loads(response.choices[0].message.content))
        if results_list is not None:
            results_list.append(output)
        return output


# --- Main Execution ---
async def main(playlist_url: str = DEFAULT_PLAYLIST, force_refresh: bool = False):
    try:
        logger.info("Starting YouTube lecture processing pipeline")

        # Stage 1: YouTube Data Collection
        yt_processor = YouTubePlaylistExtractor(force_refresh=force_refresh)
        playlist_data = yt_processor.extract_raw_playlist_data(playlist_url)
        logger.info(f"Extractered video IDs: {playlist_data.keys()}")

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
    outer_playlist_url = args.playlist if args.playlist else DEFAULT_PLAYLIST
    outer_force_refresh = args.force
    logger.info(f"Using playlist URL: {outer_playlist_url}")
    asyncio.run(main(playlist_url=outer_playlist_url, force_refresh=outer_force_refresh))
