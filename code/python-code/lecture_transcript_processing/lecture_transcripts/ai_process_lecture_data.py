import json
from pathlib import Path

import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
LECTURE_TRANSCRIPTS_DIR = "lecture_transcripts"
LECTURE_DATA_FILE = "lecture_cleaned_transcript.json"
if not Path(LECTURE_DATA_FILE).exists():
    logging.error(f"File not found: {LECTURE_DATA_FILE}, run `pull_youtube_playlist_info.py` first")
    exit()

def load_lecture_data():
    logger.debug(f"Loading lecture data from {LECTURE_DATA_FILE}")
    with open(LECTURE_DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


if __name__ == "__main__":
    lecture_data = load_lecture_data()
    for lecture in lecture_data:
        print(lecture['title'])