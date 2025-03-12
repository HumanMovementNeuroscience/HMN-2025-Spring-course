import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Type

import yaml
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.DEBUG)
# Suppress some external loggers that are too verbose for our context/taste
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
LECTURE_TRANSCRIPTS_DIR = "lecture_transcripts"
LECTURE_DATA_FILE = "lecture_transcripts/lecture_chunked_transcript.yaml"
if not Path(LECTURE_DATA_FILE).exists():
    logging.error(f"File not found: {LECTURE_DATA_FILE}, run `pull_youtube_playlist_info.py` first")
    exit()

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

OPENAI_CLIENT = AsyncOpenAI(api_key=OPENAI_API_KEY)
DEFAULT_LLM = "gpt-4o-mini"
MAX_TOKEN_LENGTH = 128_000



async def make_openai_json_mode_ai_request(client: AsyncOpenAI,
                                           system_prompt: str,
                                           prompt_model: Type[BaseModel],
                                           llm_model: str,
                                           user_input: str | None = None,
                                           results_list: list | None = None):
    messages = [{"role": "system", "content": system_prompt}]
    if user_input is not None:
        messages.append({"role": "user", "content": user_input})
    response = await client.beta.chat.completions.parse(
        model=llm_model,
        messages=messages,
        response_format=prompt_model
    )
    output = prompt_model(**json.loads(response.choices[0].message.content))
    if results_list is not None:
        results_list.append(output)
    return output


# sloppily defined twice
class TranscriptEntry(BaseModel):
    text: str
    start: float
    dur: float
    end: float | None = None



class CleanedTranscript(BaseModel):
    video_id: str = Field(..., title="Youtube video ID", description="The ID of the youtube video")
    title: str = Field(..., title="Video Title", description="The title of the video")
    transcript_chunks: list[TranscriptEntry] = Field(..., title="Transcript Chunks",
                                                     description="The transcript broken into discrete chunks")
    full_transcript: str = Field(..., title="Full Transcript", description="The full transcript of the video")


def load_lecture_data():
    logger.debug(f"Loading lecture data from {LECTURE_DATA_FILE}")
    try:
        with open(LECTURE_DATA_FILE, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.error(f"File not found: {LECTURE_DATA_FILE}")
        return None
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML file: {e}")
        return None


async def ai_cleanup_transcript(transcript: CleanedTranscript) -> CleanedTranscript:
    logger.debug(f"AI cleanup transcript - {transcript.title}")
    system_prompt = (
        "Please clean up the spoken text in the following transcript into a more grammatically correct form."
        "Remove filler words likes um, ah, etc and make the output use correct punctuation and capitalization"
        "YOU MUST MAINTAIN THE ORIGINAL MEANING AND INTENTION AND INCLUDE ALLL CONTENT!"
        "DO NOT MAKE THINGS UP! DO NOT ATTEMPT TO ADD ADDITIONAL MEANING TO THE SPOKEN TEXT!"
        "The goal is to produce a version of the spoken lecture that makes sense when written down, but which matches the meaning of th eoriginal text as closely as possible"
    )

    async def cleanup_chunk(chunk_number:int, text_chunk:TranscriptEntry):
        response = await make_openai_json_mode_ai_request(
            client=OPENAI_CLIENT,
            system_prompt=system_prompt,
            user_input=text_chunk.model_dump_json(indent=2),
            prompt_model=TranscriptEntry,
            llm_model=DEFAULT_LLM
        )
        logger.debug(f"{transcript.title} - Cleaned chunk {chunk_number} of {len(transcript.transcript_chunks)}")
        return response

    tasks = [
        cleanup_chunk(chunk_number, text_chunk)
        for chunk_number, text_chunk in enumerate(transcript.transcript_chunks)
    ]
    cleaned_chunks_responses = await asyncio.gather(*tasks)

    logger.debug(f"AI cleanup completed - {transcript.title}")
    return CleanedTranscript(
        video_id=transcript.video_id,
        title=transcript.title,
        transcript_chunks=[TranscriptEntry(**chunk.model_dump()) for chunk in cleaned_chunks_responses],
        full_transcript=" ".join([entry.text for entry in transcript.transcript_chunks])
    )

async def process_transcripts(lecture_data):
    async def process_single_transcript(lecture):
        transcript = CleanedTranscript(**lecture)
        logger.info(f"Processing: {lecture['title']}")
        return await ai_cleanup_transcript(transcript)

    tasks = [process_single_transcript(lecture) for lecture in lecture_data]
    return  await asyncio.gather(*tasks)


async def main():
    lecture_data = load_lecture_data()
    processed_transcripts = await process_transcripts(lecture_data)

    with open('lecture_transcripts/lecture_cleaned_transcript.yaml', 'w') as f:
        yaml.dump([t.model_dump() for t in processed_transcripts  ], f, default_flow_style=False)

    logger.info("Done!")


if __name__ == "__main__":
    asyncio.run(main())
