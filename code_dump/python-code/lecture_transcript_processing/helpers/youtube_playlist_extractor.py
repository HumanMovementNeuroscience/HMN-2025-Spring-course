import logging
import re
from urllib.parse import parse_qs, urlparse

import requests
import yaml
from pydantic import BaseModel, Field
from youtube_transcript_api import YouTubeTranscriptApi

from .cache_stuff import CACHE_DIRS
from .yt_models import VideoTranscript, TranscriptEntry, VideoMetadata

logger = logging.getLogger(__name__)

class YouTubePlaylistExtractor(BaseModel):
    USER_AGENT: str = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.83 Safari/537.36,gzip(gfe)'
    force_refresh: bool = Field(default=False, title="Force reprocess all data")
    chunk_interval: int = Field(default=180, title="Transcript chunk interval in seconds")

    def extract_playlist_transcripts(self, playlist_url: str) -> dict[str, VideoTranscript]:
        """Extract and process all video transcripts from a YouTube playlist."""
        logger.info(f"Processing playlist: {playlist_url}")
        video_ids = self._get_playlist_videos(playlist_url)
        
        # Check for cached videos
        existing_videos = {f.stem.split('_')[-1] for f in CACHE_DIRS['raw'].glob('*.yaml')}
        videos_to_process = video_ids if self.force_refresh else [vid for vid in video_ids if vid not in existing_videos]
        
        logger.info(f"Found {len(video_ids)} videos in playlist, processing {len(videos_to_process)}")
        
        # Process videos and collect results
        video_data_by_id = {}
        for video_id in videos_to_process:
            try:
                video_data = self.process_video(video_id)
                if video_data:
                    video_data_by_id[video_data.key_name] = video_data
            except Exception as e:
                logger.exception(f"Failed to process video {video_id}: {e}")
        
        return video_data_by_id

    def process_video(self, video_id: str) -> VideoTranscript:
        """Process a single video: fetch metadata and transcript, chunk transcript, and save."""
        try:
            # Get video metadata
            metadata = self._get_video_metadata(video_id)
            if not metadata:
                return None
                
            # Get transcript entries
            transcript_entries = self._get_transcript(video_id)
            if not transcript_entries:
                return None
                
            # Create full transcript
            full_transcript = " ".join([entry.text for entry in transcript_entries])
                
            # Chunk the transcript
            chunked_transcript = self._chunk_transcript(transcript_entries)
                
            # Create and save the final transcript
            video_transcript = VideoTranscript(
                video_id=video_id,
                metadata=metadata,
                transcript_chunks=chunked_transcript,
                full_transcript=full_transcript
            )
            
            # Save to cache
            self._save_transcript(video_transcript)
            
            return video_transcript
            
        except Exception as e:
            logger.error(f"Failed to process video {video_id}: {str(e)}")
            return None

    def _get_playlist_videos(self, playlist_url: str) -> list[str]:
        """Extract video IDs from a YouTube playlist URL."""
        query = parse_qs(urlparse(playlist_url).query)
        if not (playlist_id := query.get('list', [None])[0]):
            raise ValueError("Invalid playlist URL")

        response = requests.get(
            f'https://www.youtube.com/playlist?list={playlist_id}',
            headers={'User-Agent': self.USER_AGENT}
        )
        response.raise_for_status()
        return list(set(re.findall(r'"videoId":"([^"]{11})"', response.text)))

    def _get_video_metadata(self, video_id: str) -> VideoMetadata:
        """Fetch and extract metadata for a YouTube video."""
        try:
            video_url = f'https://www.youtube.com/watch?v={video_id}'
            logger.info(f"Requesting metadata for {video_id}")
            response = requests.get(video_url, headers={'User-Agent': self.USER_AGENT})
            response.raise_for_status()
            
            return VideoMetadata(
                title=self._extract_metadata(response.text, 'title'),
                author=self._extract_metadata(response.text, 'author'),
                view_count=self._extract_metadata(response.text, 'viewCount'),
                description=self._extract_metadata(response.text, 'shortDescription'),
                publish_date=self._extract_metadata(response.text, 'publishDate'),
                channel_id=self._extract_metadata(response.text, 'channelId'),
                duration=self._extract_metadata(response.text, 'lengthSeconds'),
                like_count=self._extract_metadata(response.text, 'likeCount'),
                tags=self._extract_metadata(response.text, 'keywords'),
            )
        except Exception as e:
            logger.error(f"Failed to get metadata for {video_id}: {str(e)}")
            return None

    @staticmethod
    def _get_transcript(video_id: str) -> list[TranscriptEntry]:
        """Get transcript for a YouTube video using youtube-transcript-api."""
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

            # Try to get an English transcript first
            try:
                transcript = transcript_list.find_transcript(['en'])
            except:
                # If no English transcript, get the first available one
                transcript = next(iter(transcript_list))

            transcript_data = transcript.fetch()

            return [
                TranscriptEntry(
                    text=item['text'],
                    start=float(item['start']),
                    dur=float(item['duration'])
                )
                for item in transcript_data
            ]
        except Exception as e:
            logger.error(f"Transcript error for {video_id}: {str(e)}")
            return []

    def _chunk_transcript(self, entries: list[TranscriptEntry]) -> list[TranscriptEntry]:
        """Chunk transcript into specified time intervals."""
        if not entries:
            return []
            
        # Sort entries by start time
        sorted_entries = sorted(entries, key=lambda x: x.start)
        
        chunks = []
        current_chunk = []
        chunk_start = 0
        chunk_end = self.chunk_interval
        
        for entry in sorted_entries:
            if entry.start >= chunk_end:
                # Save current chunk
                if current_chunk:
                    chunk_text = " ".join([e.text for e in current_chunk])
                    chunks.append(TranscriptEntry(
                        text=chunk_text,
                        start=chunk_start,
                        dur=self.chunk_interval
                    ))
                # Start new chunk
                chunk_start = chunk_end
                chunk_end = chunk_start + self.chunk_interval
                current_chunk = [entry]
            else:
                current_chunk.append(entry)
                
        # Add the final chunk
        if current_chunk:
            chunk_text = " ".join([e.text for e in current_chunk])
            chunks.append(TranscriptEntry(
                text=chunk_text,
                start=chunk_start,
                dur=self.chunk_interval
            ))
            
        return chunks
    
    def _save_transcript(self, transcript: VideoTranscript):
        """Save transcript to the cache directory."""
        output_path = CACHE_DIRS['raw'] / f'{transcript.key_name}.yaml'
        with open(output_path, 'w') as f:
            yaml.dump(transcript.model_dump(), f)
        logger.debug(f"Saved transcript for {transcript.video_id}")

    @staticmethod
    def _extract_metadata(html: str, key: str) -> str:
        """Extract a metadata field from the YouTube page HTML."""
        match = re.search(f'"{key}":"(.*?)"', html)
        return match.group(1) if match else ''