import argparse
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from base64 import b64encode
import json
from typing import Optional
import numpy as np

class CombinedPupilAnalyzer:
    def __init__(self, recording_folder: str, output_path: Optional[Path] = None):
        self.recording_folder = Path(recording_folder)
        self.output_path = output_path or self.recording_folder / "combined_analysis"
        self.output_path.mkdir(exist_ok=True)

        # Initialize components from both systems
        self.video_handler = PupilRecordingHandler.from_folder(recording_folder, MAX_WINDOW_SIZE)
        self.pupil_df, _ = self._load_and_process_data()

        # Video processing variables
        self.video_frames = []
        self.timestamps = []

    def _load_and_process_data(self):
        """Load and align pupil data with video timestamps"""
        pupil_path = self.recording_folder / "exports" / "000" / "pupil_positions.csv"
        pupil_df = pd.read_csv(pupil_path)
        pupil_df = pupil_df[pupil_df["method"] != "2d c++"]

        # Align timestamps with video
        base_time = min(self.video_handler.world_timestamps[0],
                       self.video_handler.eye0_timestamps[0],
                       self.video_handler.eye1_timestamps[0])
        pupil_df["aligned_time"] = pupil_df["pupil_timestamp"] - base_time
        return pupil_df, pupil_df

    def _generate_video_frames(self):
        """Generate synchronized video frames with timestamps"""
        self.video_handler.world_frame_index = 0  # Reset frame counter
        while True:
            try:
                frame = self.video_handler.create_synchronized_frame(annotate_images=True)
                if frame is None:
                    break
                self.video_frames.append(frame)
                self.timestamps.append(self.video_handler.world_timestamps[self.video_handler.world_frame_index])
            except Exception as e:
                logger.error(f"Error generating frame: {e}")
                break

    def create_combined_html(self):
        """Create interactive HTML with video and synchronized plots"""
        self._generate_video_frames()

        # Convert video to base64
        video_path = self.recording_folder / "synchronized_pupil_output_video.mp4"
        video_base64 = b64encode(video_path.read_bytes()).decode('utf-8')

        # Create Plotly figure
        fig = make_subplots(rows=2, cols=1,
                          row_heights=[0.7, 0.3],
                          vertical_spacing=0.05,
                          specs=[[{"type": "scatter"}], [{"type": "scatter"}]])

        # Add eye movement traces
        fig.add_trace(go.Scatter(x=self.pupil_df["aligned_time"],
                               y=self.pupil_df["phi"],
                               name="Vertical (phi)"), row=2, col=1)
        fig.add_trace(go.Scatter(x=self.pupil_df["aligned_time"],
                               y=self.pupil_df["theta"],
                               name="Horizontal (theta)"), row=2, col=1)

        # Add video frame markers
        frame_markers = go.Scatter(x=self.timestamps,
                                 y=[np.max(self.pupil_df["phi"])*1.1]*len(self.timestamps),
                                 mode='markers',
                                 marker=dict(size=8, color='red'),
                                 name="Video Frames")
        fig.add_trace(frame_markers, row=2, col=1)

        # Configure layout
        fig.update_layout(
            height=1200,
            title="Pupil Tracking Analysis",
            hovermode="x unified",
            showlegend=True,
            xaxis2=dict(title="Time (seconds)"),
            yaxis2=dict(title="Eye Position (degrees)")
        )

        # Create HTML template
        html_content = f"""
        <html>
            <head>
                <title>Pupil Tracking Analysis</title>
                <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
                <style>
                    .container {{ 
                        display: grid;
                        grid-template-rows: auto 1fr;
                        height: 100vh;
                    }}
                    #video-container {{ position: relative; }}
                    #progress {{ 
                        width: 100%;
                        height: 5px;
                        background: #ccc;
                        position: absolute;
                        bottom: 0;
                    }}
                    #progress-bar {{ 
                        height: 100%;
                        background: #ff4444;
                        width: 0%;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div id="video-container">
                        <video id="main-video" controls width="100%">
                            <source src="data:video/mp4;base64,{video_base64}" type="video/mp4">
                        </video>
                        <div id="progress">
                            <div id="progress-bar"></div>
                        </div>
                    </div>
                    <div id="plot-container"></div>
                </div>
                
                <script>
                    const video = document.getElementById('main-video');
                    const fig = {fig.to_json()};
                    const timestamps = {json.dumps(self.timestamps)};
                    
                    Plotly.newPlot('plot-container', fig.data, fig.layout);
                    
                    video.addEventListener('timeupdate', updatePlots);
                    
                    function updatePlots() {{
                        const currentTime = video.currentTime;
                        const nearestFrame = timestamps.reduce((prev, curr) => {{
                            return (Math.abs(curr - currentTime) < Math.abs(prev - currentTime) ? curr : prev;
                        }});
                        
                        // Update plot visibility
                        const update = {{
                            'xaxis.range': [currentTime - 5, currentTime + 5]
                        }};
                        Plotly.relayout('plot-container', update);
                    }}
                </script>
            </body>
        </html>
        """

        output_file = self.output_path / "combined_analysis.html"
        output_file.write_text(html_content)
        return output_file

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate combined pupil tracking analysis')
    parser.add_argument('recording_path', help='Path to Pupil Labs recording folder')
    args = parser.parse_args()

    analyzer = CombinedPupilAnalyzer(args.recording_path)
    output_file = analyzer.create_combined_html()
    logger.info(f"Analysis complete. Output file: {output_file}")