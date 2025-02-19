import json
import re
from urllib.parse import parse_qs, urlparse

import requests
import yaml
from pydantic import BaseModel


# --- Pydantic Models ---
class TranscriptEntry(BaseModel):
    text: str
    start: float
    dur: float


class VideoMetadata(BaseModel):
    title: str
    author: str
    viewCount: str
    description: str
    publish_date: str
    channel_id: str
    duration: str
    likeCount: str | None
    tags: str | None


class VideoData(BaseModel):
    video_id: str
    metadata: VideoMetadata
    transcript: list[TranscriptEntry]

    def chunk_transcript(self, interval_seconds: int = 600) -> list[dict]:
        chunks = []
        current_chunk = []
        current_end = interval_seconds

        for entry in sorted(self.transcript, key=lambda x: x.start):
            if entry.start > current_end:
                # Save current chunk
                chunk_text = " ".join([e.text for e in current_chunk])
                chunks.append({
                    "start": current_end - interval_seconds,
                    "end": current_end,
                    "text": chunk_text
                })
                # Reset for next chunk
                current_chunk = [entry]
                current_end += interval_seconds
            else:
                current_chunk.append(entry)

        # Add the final chunk
        if current_chunk:
            chunk_text = " ".join([e.text for e in current_chunk])
            chunks.append({
                "start": current_end - interval_seconds,
                "end": current_end,
                "text": chunk_text
            })

        return chunks


class YoutubeFetcher:
    USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.83 Safari/537.36,gzip(gfe)'
    RE_YOUTUBE = re.compile(
        r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})', re.I)
    RE_XML_TRANSCRIPT = re.compile(r'<text start="([^"]*)" dur="([^"]*)">([^<]*)<\/text>')

    @classmethod
    def get_playlist_videos(cls, playlist_url):
        try:
            # Extract playlist ID from URL
            query = parse_qs(urlparse(playlist_url).query)
            playlist_id = query.get('list', [None])[0]

            if not playlist_id:
                raise ValueError("Invalid playlist URL")

            # Fetch playlist page
            response = requests.get(
                f'https://www.youtube.com/playlist?list={playlist_id}',
                headers={'User-Agent': cls.USER_AGENT}
            )
            response.raise_for_status()

            # Extract video IDs from playlist page
            video_ids = re.findall(r'"videoId":"([^"]{11})"', response.text)
            return list(set(video_ids))  # Remove duplicates

        except Exception as e:
            print(f"Error getting playlist: {e}")
            return []

    @classmethod
    def get_video_data(cls, video_id):
        try:
            # Fetch video page
            video_url = f'https://www.youtube.com/watch?v={video_id}'
            response = requests.get(video_url, headers={'User-Agent': cls.USER_AGENT})
            response.raise_for_status()
            html = response.text

            # Extract metadata
            metadata = {
                'title': cls._extract_metadata(html, 'title'),
                'author': cls._extract_metadata(html, 'author'),
                'viewCount': cls._extract_metadata(html, 'viewCount'),
                'description': cls._extract_metadata(html, 'shortDescription'),
                'publish_date': cls._extract_metadata(html, 'publishDate'),
                'channel_id': cls._extract_metadata(html, 'channelId'),
                'duration': cls._extract_metadata(html, 'lengthSeconds'),
                'likeCount': cls._extract_metadata(html, 'likeCount'),
                'tags': cls._extract_metadata(html, 'keywords'),
            }

            # Extract transcript
            transcript = cls._get_transcript(html, video_id)

            return VideoData(
                video_id=video_id,
                metadata=VideoMetadata(**metadata),
                transcript=[TranscriptEntry(text=entry['text'],
                                            start=float(entry['start']),
                                            dur=float(entry['dur'])) for entry in transcript]
            )

        except Exception as e:
            print(f"Error processing video {video_id}: {e}")
            raise e

    @classmethod
    def _get_transcript(cls, html, video_id):
        try:
            # Find captions JSON
            captions_json = html.split('"captions":')[1].split(',"videoDetails')[0]
            captions = json.loads(captions_json.replace('\n', ''))['playerCaptionsTracklistRenderer']

            if not captions.get('captionTracks'):
                return "No transcript available"

            # Get first available transcript
            transcript_url = captions['captionTracks'][0]['baseUrl']
            transcript_res = requests.get(transcript_url, headers={'User-Agent': cls.USER_AGENT})
            transcript_res.raise_for_status()

            # Parse XML transcript
            matches = cls.RE_XML_TRANSCRIPT.findall(transcript_res.text)
            return [{'text': text, 'start': start, 'dur': dur} for start, dur, text in matches]

        except Exception as e:
            print(f"Transcript error for {video_id}: {e}")
            raise e

    @staticmethod
    def _extract_metadata(html, key):
        match = re.search(f'"{key}":"(.*?)"', html)
        return match.group(1) if match else None


# --- New Markdown Generation Functions ---
def format_duration(seconds: float) -> str:
    minutes, sec = divmod(seconds, 60)
    return f"{int(minutes):02d}:{int(sec):02d}"


def generate_markdown(videos: list[VideoData]) -> str:
    md = ["# YouTube Playlist Transcripts\n"]

    for video in videos:
        # Video Header
        md.append(f"## {video.metadata.title}\n")
        md.append(f"**Author**: {video.metadata.author}  \n")
        md.append(f"**Duration**: {format_duration(float(video.metadata.duration))}  \n")
        md.append(f"**Published**: {video.metadata.publish_date}  \n")
        md.append(f"**Views**: {video.metadata.viewCount}  \n\n")

        # Transcript Chunks
        md.append("### Transcript Summary\n")
        for chunk in video.chunk_transcript():
            start_time = format_duration(chunk['start'])
            end_time = format_duration(chunk['end'])
            md.append(f"#### {start_time} - {end_time}\n")
            md.append(f"{chunk['text']}\n\n")

        md.append("---\n")

    return "\n".join(md)


# --- Updated Main Function ---
def main():
    playlist_url = 'https://youtube.com/playlist?list=PLWxH2Ov17q5HDfMBJxD_cE1lowM1cr_BV'

    fetcher = YoutubeFetcher()
    video_ids = fetcher.get_playlist_videos(playlist_url)

    if not video_ids:
        print("No videos found in playlist")
        return

    videos = [v for vid in video_ids if (v := fetcher.get_video_data(vid)) is not None]

    # Save YAML
    with open('playlist_data.yaml', 'w') as f:
        yaml.dump([v.dict() for v in videos], f, default_flow_style=False)

    # Save Markdown
    with open('playlist_transcripts.md', 'w', encoding='utf-8') as f:
        f.write(generate_markdown(videos))

    print(f"Saved data for {len(videos)} videos (YAML + MD)")


if __name__ == "__main__":
    main()
