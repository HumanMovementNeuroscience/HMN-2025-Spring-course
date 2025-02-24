import { YoutubeTranscript } from 'youtube-transcript';

async function fetchTranscriptWithRetry(videoIdOrUrl) {
  let success = false;
  let attempt = 0;

  while (!success) {
    attempt += 1;
    console.log(`Attempt ${attempt}: Fetching transcript...`);

    try {
      const transcript = await YoutubeTranscript.fetchTranscript(videoIdOrUrl);
      console.log('Transcript successfully fetched:', transcript);
      success = true;
    } catch (error) {
      console.log(`Attempt ${attempt} failed. Transcript not available yet. Retrying in 1 minute...`);
    }

    if (!success) {
      await new Promise(resolve => setTimeout(resolve, 60 * 1000)); // Wait for 1 minute before retrying
    }
  }
}

// Replace 'VIDEO_ID_OR_URL' with the actual YouTube video ID or URL you want to check
// const videoIdOrUrl = 'https://youtu.be/F4FNNmuAq74';
const videoIdOrUrl = 'https://youtu.be/VfSQ43VBG28' //HMN24 - 01 - Intro to Data Collection
fetchTranscriptWithRetry(videoIdOrUrl);
