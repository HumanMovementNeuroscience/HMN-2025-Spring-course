import pytube
import yaml
from youtube_transcript_api import YouTubeTranscriptApi
from pytube.exceptions import VideoUnavailable


def download_youtube_playlist(playlist_url: str):
    try:
        playlist = pytube.Playlist(playlist_url)
        playlist._video_regex = r'"url":"(/watch\?v=[\w-]*)"'  # Force new regex pattern
        print(f'Downloading: {playlist.title}')

        video_data = []

        for url in playlist.video_urls:
            try:
                video = pytube.YouTube(url)
                print(f'Processing video: {video.title}')

                # Download video
                video.streams.get_lowest_resolution().download(output_path='videos')

                # Get transcript
                try:
                    transcript = YouTubeTranscriptApi.get_transcript(video.video_id)
                    transcript_text = " ".join([entry['text'] for entry in transcript])
                except Exception as e:
                    transcript_text = f"Transcript not available: {e}"

                # Collect metadata
                info = {
                    'title': video.title,
                    'description': video.description,
                    'length': video.length,
                    'views': video.views,
                    'author': video.author,
                    'publish_date': video.publish_date.strftime('%Y-%m-%d') if video.publish_date else None,
                    'transcript': transcript_text
                }
                video_data.append(info)

            except VideoUnavailable:
                print(f'Video {url} is unavailable')
                continue

        with open('video_data.yaml', 'w') as yaml_file:
            yaml.dump(video_data, yaml_file, default_flow_style=False)

        print('Download complete and data saved to video_data.yaml')

    except Exception as e:
        print(f'An error occurred: {e}')


if __name__ == "__main__":
    playlist_url = 'https://www.youtube.com/embed/videoseries?list=PLWxH2Ov17q5HDfMBJxD_cE1lowM1cr_BV'
    download_youtube_playlist(playlist_url)