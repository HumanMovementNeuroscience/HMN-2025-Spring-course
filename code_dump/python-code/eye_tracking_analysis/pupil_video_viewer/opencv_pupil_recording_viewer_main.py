import json
import logging
from base64 import b64encode
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from numpydantic import NDArray
from plotly.subplots import make_subplots
from pydantic import BaseModel, ConfigDict

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
MAX_WINDOW_SIZE = (1920, 1080)


class PupilRecordingHandler(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    video_folder: str
    world_frame_index:int = 0
    world_timestamps: NDArray
    eye0_timestamps: NDArray
    eye1_timestamps: NDArray
    world_video_cap: cv2.VideoCapture
    eye0_video_cap: cv2.VideoCapture
    eye1_video_cap: cv2.VideoCapture
    output_video_writer: cv2.VideoWriter | None = None

    frame_count: int

    frame_size : tuple[int, int] = (1920, 1080)  # Default frame size for the output video
    @classmethod
    def from_folder(cls, pupil_recording_folder: str, max_window_size: tuple[int, int]):

        if not Path(pupil_recording_folder).exists():
            raise ValueError(f"Video folder does not exist: {pupil_recording_folder}")
        world_timestamps = np.load(str(Path(pupil_recording_folder) / "world_timestamps.npy"))
        eye0_timestamps = np.load(str(Path(pupil_recording_folder) / "eye0_timestamps.npy"))
        eye1_timestamps = np.load(str(Path(pupil_recording_folder) / "eye1_timestamps.npy"))
        world_video = str(Path(pupil_recording_folder) / "world.mp4")
        eye0_video = str(Path(pupil_recording_folder) / "eye0.mp4")
        eye1_video = str(Path(pupil_recording_folder) / "eye1.mp4")

        world_cap = cv2.VideoCapture(world_video)
        eye0_cap = cv2.VideoCapture(eye0_video)
        eye1_cap = cv2.VideoCapture(eye1_video)
        if not (world_cap.isOpened()):
            raise ValueError(f"Could not open world video: {world_video}")
        if not (eye0_cap.isOpened()):
            raise ValueError(f"Could not open eye0 video: {eye0_video}")
        if not (eye1_cap.isOpened()):
            raise ValueError(f"Could not open eye1 video: {eye1_video}")

        world_video_framerate = np.mean(np.diff(world_timestamps))**-1
        eye0_video_framerate = np.mean(np.diff(eye0_timestamps))**-1
        eye1_video_framerate = np.mean(np.diff(eye1_timestamps))**-1
        slowest_framerate = min(world_video_framerate, eye0_video_framerate, eye1_video_framerate)

        output_video_path = str(Path(pupil_recording_folder) / f"synchronized_pupil_output_video.mp4")
        fourcc = cv2.VideoWriter_fourcc(*'x264')
        output_video_writer = cv2.VideoWriter(output_video_path, fourcc, float(slowest_framerate),
                                                  max_window_size)
        if not output_video_writer.isOpened():
            raise ValueError(f"Could not open output video writer: {output_video_path}")
        base_recording_timestamp = min(world_timestamps[0], eye0_timestamps[0], eye1_timestamps[0])
        world_timestamps -= base_recording_timestamp
        eye0_timestamps -= base_recording_timestamp
        eye1_timestamps -= base_recording_timestamp


        return cls(
            video_folder=pupil_recording_folder,
            world_timestamps=world_timestamps,
            eye0_timestamps=eye0_timestamps,
            eye1_timestamps=eye1_timestamps,
            world_video_cap=world_cap,
            eye0_video_cap=eye0_cap,
            eye1_video_cap=eye1_cap,
            frame_count=int(world_cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            output_video_writer=output_video_writer,
            frame_size = max_window_size
        )

    def create_synchronized_frame(self, annotate_images: bool) -> np.ndarray|None:
        """Create a grid of video images synchronized at the given timestamp.
        Each video stream may have different framerates, so we find the closest frame
        in each video to the current timestamp.

        Args:
            current_time: The timestamp to synchronize frames to
            annotate_images: Whether to add annotations to the frames

        Returns:
            np.ndarray: Combined frame containing world and eye videos in a grid layout
        """
        # Find the closest frame indices for each video stream
        self.world_frame_index += 1
        logger.debug(f"Current world frame index: {self.world_frame_index} of {self.frame_count}")
        if self.world_frame_index >= len(self.world_timestamps)-1:
            logger.info(f"Reached end of world video: {self.world_frame_index}/{len(self.world_timestamps)}")
            return None
        current_time = self.world_timestamps[self.world_frame_index]
        eye0_frame_index = np.abs(self.eye0_timestamps - current_time).argmin()
        eye1_frame_index = np.abs(self.eye1_timestamps - current_time).argmin()

        # Get the actual timestamps for the frames we'll be showing
        actual_eye0_time = self.eye0_timestamps[eye0_frame_index]
        actual_eye1_time = self.eye1_timestamps[eye1_frame_index]

        # Seek to the correct frames in each video
        self.world_video_cap.set(cv2.CAP_PROP_POS_FRAMES, self.world_frame_index)
        self.eye0_video_cap.set(cv2.CAP_PROP_POS_FRAMES, eye0_frame_index)
        self.eye1_video_cap.set(cv2.CAP_PROP_POS_FRAMES, eye1_frame_index)

        # Read the frames
        success_w, world_frame = self.world_video_cap.read()
        success_e0, eye0_frame = self.eye0_video_cap.read()
        success_e1, eye1_frame = self.eye1_video_cap.read()
        if not (success_w and success_e0 and success_e1):
            logger.error(f"Failed to read frames at timestamp: {current_time} - "
                         f"World: {success_w}, Eye0: {success_e0}, Eye1: {success_e1}")
            raise ValueError(f"Failed to read frames at timestamp {current_time}")

        if world_frame is None or eye0_frame is None or eye1_frame is None:
            raise ValueError(f"Failed to read frames at timestamp {current_time}")

        # Calculate dimensions for the output frame
        output_width, output_height = self.frame_size

        # Calculate maximum dimensions for each region
        world_max_height = int(output_height * 0.6)
        world_max_width = int(output_width * 0.8)
        eye_max_height = int(output_height * 0.35)
        eye_max_width = int(output_width * 0.4)

        # Resize frames maintaining aspect ratio
        world_scale = min(world_max_width / world_frame.shape[1],
                          world_max_height / world_frame.shape[0])
        world_new_width = int(world_frame.shape[1] * world_scale)
        world_new_height = int(world_frame.shape[0] * world_scale)
        world_frame_resized = cv2.resize(world_frame, (world_new_width, world_new_height))

        eye_scale = min(eye_max_width / eye0_frame.shape[1],
                        eye_max_height / eye0_frame.shape[0])
        eye0_new_width = int(eye0_frame.shape[1] * eye_scale)
        eye0_new_height = int(eye0_frame.shape[0] * eye_scale)
        eye1_new_width = int(eye1_frame.shape[1] * eye_scale)
        eye1_new_height = int(eye1_frame.shape[0] * eye_scale)
        eye0_frame_resized = cv2.resize(eye0_frame, (eye0_new_width, eye0_new_height))
        eye1_frame_resized = cv2.resize(eye1_frame, (eye1_new_width, eye1_new_height))

        # Create empty output frame
        output_frame = np.zeros((output_height, output_width, 3), dtype=np.uint8)

        # Calculate centered positions for placing frames
        world_x = (output_width - world_new_width) // 2
        world_y = int(output_height * 0.05) + (world_max_height - world_new_height) // 2

        eye0_x = int(output_width * 0.05) + (eye_max_width - eye0_new_width) // 2
        eye1_x = int(output_width * 0.55) + (eye_max_width - eye1_new_width) // 2
        eye_base_y = int(output_height * 0.65)
        eye0_y = eye_base_y + (eye_max_height - eye0_new_height) // 2
        eye1_y = eye_base_y + (eye_max_height - eye1_new_height) // 2

        # Place frames in the output image
        output_frame[world_y:world_y + world_new_height,
        world_x:world_x + world_new_width] = world_frame_resized
        output_frame[eye0_y:eye0_y + eye0_new_height,
        eye0_x:eye0_x + eye0_new_width] = eye0_frame_resized
        output_frame[eye1_y:eye1_y + eye1_new_height,
        eye1_x:eye1_x + eye1_new_width] = eye1_frame_resized

        if annotate_images:
            # Add timestamp annotations showing both requested and actual timestamps
            world_text = f"World: {current_time:.3f}s (frame {self.world_frame_index})"
            eye0_text = f"Eye 0: {actual_eye0_time:.3f}s (frame {eye0_frame_index})"
            eye1_text = f"Eye 1: {actual_eye1_time:.3f}s (frame {eye1_frame_index})"

            cv2.putText(output_frame, world_text, (world_x, world_y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            cv2.putText(output_frame, eye0_text, (eye0_x, eye_base_y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            cv2.putText(output_frame, eye1_text, (eye1_x, eye_base_y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        # Write frame to output video if writer exists
        if not self.output_video_writer.isOpened():
            raise ValueError(f"Output video writer is not opened: {self.output_video_writer}")
        self.output_video_writer.write(output_frame)

        return output_frame

    def close(self):
        """Clean up resources."""
        logger.info("VideoHandler closing")
        self.output_video_writer.release()
        self.eye0_video_cap.release()
        self.eye1_video_cap.release()
        self.world_video_cap.release()

class PupilRecordingViewerMain(BaseModel):
    recording_folder: str
    max_window_size: tuple[int, int]
    recording_handler: PupilRecordingHandler
    is_playing: bool = True
    playback_speed: int = 1.0 # Playback speed multiplier (1.0 = real-time)
    zoom_scale: float = 1.0
    zoom_center: tuple[int, int] = (0, 0)
    active_cell: tuple[int, int] | None = None  # Track which cell the mouse is in

    @classmethod
    def create(cls, pupil_recording_folder: str,
               max_window_size: tuple[int, int] = MAX_WINDOW_SIZE):

        return cls(recording_handler=PupilRecordingHandler.from_folder(pupil_recording_folder, max_window_size),
                   recording_folder=pupil_recording_folder,
                   max_window_size=max_window_size)


    def _handle_keypress(self, key: int):
        if key == ord('q') or key == 27:  # q or ESC
            return False
        elif key == 32:  # spacebar
            self.is_playing = not self.is_playing
        elif key == ord('r'):  # reset zoom
            for video in self.recording_handler.videos:
                video.zoom_state.reset()
        return True


    def run(self):
        """Run the video grid viewer."""
        cv2.namedWindow(self.recording_folder, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.recording_folder, *self.max_window_size)

        try:
            while True:
                key = cv2.waitKey(1) & 0xFF
                if not self._handle_keypress(key):
                    break
                view_image = self.recording_handler.create_synchronized_frame( annotate_images=True)
                if view_image is None:
                    logger.info("No more frames to display.")
                    break
                # cv2.imshow(str(self.recording_folder), view_image)
        finally:
            self.recording_handler.close()

class CombinedPupilAnalyzer:
    def __init__(self, recording_folder: str, output_path: Optional[Path] = None):
        self.recording_folder = Path(recording_folder)
        self.output_path = output_path or self.recording_folder / "combined_analysis"
        self.output_path.mkdir(exist_ok=True)
        self.sync_video_path = self.recording_folder / "synchronized_pupil_output_video.mp4"

        # Load pupil data first
        self.pupil_df = self._load_pupil_data()

        # Initialize video handler and create synchronized video if needed
        self._init_video_processing()

    def _load_pupil_data(self):
        """Load and process pupil position data"""
        pupil_path = self.recording_folder / "exports" / "000" / "pupil_positions.csv"
        pupil_df = pd.read_csv(pupil_path)
        pupil_df = pupil_df[pupil_df["method"] != "2d c++"]
        return pupil_df

    def _init_video_processing(self):
        """Initialize video processing and create synchronized video if needed"""
        if not self.sync_video_path.exists():
            logger.info("Synchronized video not found. Creating new synchronized video...")
            self.video_handler = PupilRecordingHandler.from_folder(str(self.recording_folder), MAX_WINDOW_SIZE)

            # Create synchronized video
            while True:
                frame = self.video_handler.create_synchronized_frame(annotate_images=True)
                if frame is None:
                    break

            self.video_handler.close()
            logger.info("Finished creating synchronized video")
        else:
            logger.info("Using existing synchronized video")

        # Reinitialize video handler for timestamp access
        self.video_handler = PupilRecordingHandler.from_folder(str(self.recording_folder), MAX_WINDOW_SIZE)

        # Align timestamps
        base_time = min(self.video_handler.world_timestamps[0],
                       self.video_handler.eye0_timestamps[0],
                       self.video_handler.eye1_timestamps[0])
        self.pupil_df["aligned_time"] = self.pupil_df["pupil_timestamp"] - base_time
        self.timestamps = self.video_handler.world_timestamps[:self.video_handler.frame_count].tolist()

    def create_combined_html(self):
        """Create interactive HTML with video and synchronized plots"""
        # Convert video to base64
        video_base64 = b64encode(self.sync_video_path.read_bytes()).decode('utf-8')

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
                                 y=[np.max(self.pupil_df["phi"]) * 1.1] * len(self.timestamps),
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

        # Create and save HTML file
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
                            return (Math.abs(curr - currentTime) < Math.abs(prev - currentTime) ? curr : prev);
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
        self.video_handler.close()
        return output_file

if __name__ == '__main__':
    PUPIL_RECORDING_PATH = Path(r'C:\Users\jonma\recordings\2025_03_10\001')
    try:
        viewer = PupilRecordingViewerMain.create(pupil_recording_folder=str(PUPIL_RECORDING_PATH))
        viewer.run()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
    # analyzer = CombinedPupilAnalyzer(str(PUPIL_RECORDING_PATH))
    # output_file = analyzer.create_combined_html()