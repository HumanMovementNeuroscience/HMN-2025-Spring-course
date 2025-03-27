import re
from pydantic import BaseModel

class TranscriptEntry(BaseModel):
    text: str
    start: float
    dur: float
    end: float = None

    def model_post_init(self, __context) -> None:
        # Calculate end time if not provided
        if self.end is None:
            self.end = self.start + self.dur

class VideoMetadata(BaseModel):
    title: str
    author: str
    view_count: str
    description: str
    publish_date: str
    channel_id: str
    duration: str
    like_count: str = None
    tags: str = None

    @property
    def clean_title(self) -> str:
        return re.sub(r'[^a-zA-Z0-9 ]', '', self.title).replace(' ', '_').lower()

class VideoTranscript(BaseModel):
    video_id: str
    metadata: VideoMetadata
    transcript_chunks: list[TranscriptEntry]
    full_transcript: str = ""

    @property
    def key_name(self) -> str:
        return f"{self.metadata.clean_title}_{self.video_id}"

class ProcessedTranscript(BaseModel):
    video_id: str
    title: str
    transcript_chunks: list[TranscriptEntry]
    full_transcript: str = ""

    @property
    def key_name(self) -> str:
        return f"{self.title}_{self.video_id}"