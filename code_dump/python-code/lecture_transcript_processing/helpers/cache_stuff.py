from pathlib import Path

CACHE_DIRS = {
    'raw': Path(__file__).parent / "lecture_transcripts/raw",
    'cleaned': Path(__file__).parent / "lecture_transcripts/cleaned",
    'outlines': Path(__file__).parent / "lecture_transcripts/outlines",
    'themes': Path(__file__).parent / "lecture_transcripts/themes"
}

for directory in CACHE_DIRS.values():
    directory.mkdir(parents=True, exist_ok=True)

