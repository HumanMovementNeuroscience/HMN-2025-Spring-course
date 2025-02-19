import pytube
import yaml
from youtube_transcript_api import YouTubeTranscriptApi

def download_youtube_playlist(playlist_url):
    try:
        playlist = pytube.Playlist(playlist_url)
        print(f'Downloading: {playlist.title}')
        
        video_data = []

        for video in playlist.videos:
            print(f'Processing video: {video.title}')
            # Download video
            video.streams.first().download(output_path='videos', filename=video.title)

            # Get video transcript
            try:
                transcript = YouTubeTranscriptApi.get_transcript(video.video_id)
                transcript_text = " ".join([entry['text'] for entry in transcript])
            except Exception as e:
                transcript_text = f"Transcript not available: {e}"

            # Collect video information
            info = {
                'title': video.title,
                'description': video.description,
                'length': video.length,
                'views': video.views,
                'author': video.author,
                'publish_date': video.publish_date.strftime('%Y-%m-%d'),
                'transcript': transcript_text
            }
            video_data.append(info)

        # Save the video information to a YAML file
        with open('video_data.yaml', 'w') as yaml_file:
            yaml.dump(video_data, yaml_file, default_flow_style=False)

        print('Download complete and data saved to video_data.yaml')

    except Exception as e:
        print(f'An error occurred: {e}')

if __name__ == "__main__":
    playlist_url = 'https://www.youtube.com/playlist?list=PLWxH2Ov17q5HDfMBJxD_cE1lowM1cr_BV'
    download_youtube_playlist(playlist_url)