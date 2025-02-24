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
LECTURE_DATA_FILE = "lecture_transcripts/lecture_cleaned_transcript.yaml"
if not Path(LECTURE_DATA_FILE).exists():
    logging.error(f"File not found: {LECTURE_DATA_FILE}, run `ai_cleanup_lecture_data.py` first")
    exit()

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

OPENAI_CLIENT = AsyncOpenAI(api_key=OPENAI_API_KEY)
DEFAULT_LLM = "gpt-4o-mini"
MAX_TOKEN_LENGTH = 128_000

async def make_openai_text_generation_ai_request(client: AsyncOpenAI,
                                           system_prompt: str,
                                           llm_model: str):
    messages = [
        {
            "role": "system",
            "content": system_prompt
        }
    ]
    response = await client.beta.chat.completions.parse(
        model=llm_model,
        messages=messages,
        temperature=0.0,
    )
    output = response.choices[0].message.content
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



async def ai_outline_transcript(transcript: CleanedTranscript) -> str:
    logger.debug(f"AI cleanup transcript - {transcript.title}")
    base_system_prompt = ("""
         You are working on generating a comprehensive outline of the content of a transcribed lecture the title of th electure is: \n\n{LECTURE_TITLE}\n\n
         You are being given the lecture transcript piece by piece and generating a running outline based on the present chunk along with the outline from previous iterations
         You are currently on chunk number {CHUNK_NUMBER} of {TOTAL_CHUNK_COUNT}
         The outline from the previous iterations is: \n\n```\n\n {PREVIOUS_OUTLINE}\n\n```\n\n
         The current chunk of text you are integrating into the outline is: \n\n```\n\n {CURRENT_CHUNK}\n\n```\n\n
         Your response should be in the form of a markdown formatted outline with a #H1 title, ##H2 headings for the major topics, ###H3 headings for the minor topics, and bulleted outline sentences for the content itself
         Focus on the CONTENT of the lecture, not information that is incidental to the record (i.e. Greeting the students, acknowledging forgotten equipment, etc)
         De-emphasize  course related admin stuff about assignments and due dates, adn focus on the scientific and philophical core content of the lecture. 
         Focus on declarative statements rather than vage referential ones, for example, don't say stuff like:
         ```
         ## Introduction to the Lecture
            - Overview of the course structure and expectations.
            - Emphasis on student engagement and personal interests in the subject matter.
            
        ## The Role of AI in Education
            - AI's ability to adapt to student interests compared to traditional curricula.
            - Encouragement for students to explore their unique paths in human perceptual motor neuroscience.
        ```
        
        Instead, include the actual CONTENT of what was said on those topics! A person reading this outline should walk away with the same main points as someone who watched the lecture.  
         Do not respond with ANY OTHER TEXT besides the running outline, which integrates the current text chunk with the outline from previous iterations
         """
                          )
    running_outline = "# " + transcript.title + "\n"
    try:

        async def outline_chunk(chunk_number: int, text_chunk: TranscriptEntry, running_outline: str):
            system_prompt = base_system_prompt.format(
                LECTURE_TITLE=transcript.title,
                CHUNK_NUMBER=chunk_number + 1,
                TOTAL_CHUNK_COUNT=len(transcript.transcript_chunks),
                PREVIOUS_OUTLINE=running_outline,
                CURRENT_CHUNK=text_chunk.text,
            )
            response = await make_openai_text_generation_ai_request(
                client=OPENAI_CLIENT,
                system_prompt=system_prompt,
                llm_model=DEFAULT_LLM
            )
            logger.debug(f"{transcript.title} - Outlined chunk {chunk_number + 1} of {len(transcript.transcript_chunks)}")
            return response

        for chunk_number, text_chunk in enumerate(transcript.transcript_chunks):
            running_outline = await outline_chunk(chunk_number, text_chunk, running_outline)

        logger.debug(f"AI outline completed - {transcript.title}")
    except Exception as e:
        logger.error(f"Error adding AI outline : {e}")
    return running_outline


async def process_transcripts(lecture_data) -> list[str]:
    async def process_single_transcript(lecture):
        transcript = CleanedTranscript(**lecture)
        logger.info(f"Processing: {lecture['title']}")
        return await ai_outline_transcript(transcript)

    tasks = [process_single_transcript(lecture) for lecture in lecture_data]
    processed_transcripts =  await asyncio.gather(*tasks)
    outline_tasks = [await ai_outline_transcript(transcript) for transcript in processed_transcripts]
    outline_results = await asyncio.gather(*outline_tasks)
    return  outline_results


async def main():
    lecture_data = load_lecture_data()
    outline_results= await process_transcripts(lecture_data)
    outline_text_output =[f"\n\n{t}\n\n========\n\n" for t in outline_results  ]
    with open('lecture_transcripts/lecture_outlines.md', 'w') as f:
        f.writelines(outline_text_output)

    logger.info("Done!")


if __name__ == "__main__":
    asyncio.run(main())
