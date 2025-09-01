import asyncio
import logging

from helpers.ai_yt_transcript_processor import AITranscriptProcessor
from helpers.youtube_playlist_extractor import YouTubePlaylistExtractor

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s | %(levelname)s | %(name)s | %(lineno)d | %(message)s',)
logger = logging.getLogger(__name__)

# Suppress some external loggers
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

async def main(playlist_url: str, force_refresh: bool = False):
    try:
        logger.info("Starting YouTube lecture processing pipeline")

        # Extract transcripts from playlist
        yt_processor = YouTubePlaylistExtractor(force_refresh=force_refresh)
        video_data = await yt_processor.extract_playlist_transcripts(playlist_url)
        logger.info(f"Processed {len(video_data)} videos from playlist")

        # AI processing (if you're keeping this)
        ai_processor = AITranscriptProcessor(force_refresh=force_refresh)
        await ai_processor.process_transcripts()

        logger.info("Pipeline completed successfully")
    except Exception as e:
        logger.error(f"Pipeline failed: {str(e)}")
        raise

if __name__ == "__main__":
    # YOUTUBE_PLAYLIST = "https://youtube.com/playlist?list=PLWxH2Ov17q5HDfMBJxD_cE1lowM1cr_BV" #HMN25
    # YOUTUBE_PLAYLIST = "https://youtube.com/playlist?list=PLWxH2Ov17q5HRyRc7_HD5baSYB6kBgsTj" #HMN24
    YOUTUBE_PLAYLIST = "https://www.youtube.com/playlist?list=PLWxH2Ov17q5EQlt0L5bja56tK6xT1U7ws" # FMC LIVESTREAMS
    logger.info(f"Using playlist URL: {YOUTUBE_PLAYLIST}")
    asyncio.run(main(playlist_url=YOUTUBE_PLAYLIST, force_refresh=True))