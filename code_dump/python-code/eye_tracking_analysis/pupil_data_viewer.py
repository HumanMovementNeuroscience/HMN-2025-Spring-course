import argparse
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import webbrowser


def process_data(pupil_data_path):
    """Load and preprocess pupil tracking data"""
    pupil_df = pd.read_csv(pupil_data_path)

    # Filter out '2d c++' method data
    filtered_df = pupil_df[pupil_df["method"] != "2d c++"]
    return pupil_df, filtered_df


def create_visualizations(pupil_df, filtered_df, analysis_dir):
    """Create and save all visualizations to HTML files"""
    # Create analysis directory if it doesn't exist
    analysis_dir.mkdir(parents=True, exist_ok=True)

    # 1. Time Series Plot
    fig_time = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.02)
    fig_time.add_trace(go.Scatter(y=filtered_df["phi"], mode="lines+markers", name="phi"), row=1, col=1)
    fig_time.add_trace(go.Scatter(y=filtered_df["theta"], mode="lines+markers", name="theta"), row=2, col=1)
    fig_time.update_layout(height=800, width=800, title_text="Pupil Positions Time Series")
    time_series_path = analysis_dir / "time_series.html"
    fig_time.write_html(str(time_series_path))

    # 2. Theta vs Phi Scatter
    fig_scatter = go.Figure()
    fig_scatter.add_trace(go.Scatter(
        x=filtered_df["theta"],
        y=filtered_df["phi"],
        mode='lines+markers',
        name='Gaze'
    ))
    fig_scatter.update_layout(title_text="Theta vs Phi", xaxis_title='Theta', yaxis_title='Phi')
    scatter_path = analysis_dir / "theta_phi_scatter.html"
    fig_scatter.write_html(str(scatter_path))

    # 3. 3D Gaze Visualization
    fig_3d = go.Figure()
    fig_3d.add_trace(go.Scatter3d(
        x=filtered_df["theta"],
        y=filtered_df["phi"],
        z=filtered_df["diameter_3d"],
        mode='lines+markers',
        name='3D Gaze'
    ))
    fig_3d.update_layout(scene=dict(
        xaxis_title='Theta',
        yaxis_title='Phi',
        zaxis_title='Diameter 3D'
    ))
    td_path = analysis_dir / "3d_gaze.html"
    fig_3d.write_html(str(td_path))

    # 4. Gaze Position Over Time
    fig_time_pos = go.Figure()
    fig_time_pos.add_trace(go.Scatter3d(
        x=pupil_df["norm_pos_x"],
        y=pupil_df["norm_pos_y"],
        z=pupil_df["pupil_timestamp"],
        mode='lines+markers',
        name='Gaze Over Time'
    ))
    fig_time_pos.update_layout(scene=dict(
        xaxis_title='X Position',
        yaxis_title='Y Position',
        zaxis_title='Time'
    ))
    time_pos_path = analysis_dir / "gaze_over_time.html"
    fig_time_pos.write_html(str(time_pos_path))

    # 5. 3D Circle Centers
    fig_circle = go.Figure()
    fig_circle.add_trace(go.Scatter3d(
        x=pupil_df["circle_3d_center_x"],
        y=pupil_df["circle_3d_center_y"],
        z=pupil_df["circle_3d_center_z"],
        mode='lines+markers',
        name='3D Centers'
    ))
    fig_circle.update_layout(scene=dict(
        xaxis_title='X Center',
        yaxis_title='Y Center',
        zaxis_title='Z Center'
    ))
    circle_path = analysis_dir / "3d_centers.html"
    fig_circle.write_html(str(circle_path))

    return [time_series_path, scatter_path, td_path, time_pos_path, circle_path]


def main(recording_path):
    pupil_path = Path(recording_path)
    analysis_dir = pupil_path.parent / "analysis"

    # Process data
    raw_df, filtered_df = process_data(pupil_path)

    # Save filtered data
    filtered_path = analysis_dir / "filtered_pupil_data.csv"
    filtered_df.to_csv(filtered_path, index=False)

    # Create visualizations
    html_files = create_visualizations(raw_df, filtered_df, analysis_dir)

    # Open all visualizations in browser
    for html_file in html_files:
        webbrowser.open_new_tab(f"file://{html_file.resolve()}")


if __name__ == "__main__":
    # Hardcoded default path
    DEFAULT_RECORDING_PATH = r"C:\Users\jonma\recordings\2024_10_22\000\exports\000\pupil_positions.csv"

    parser = argparse.ArgumentParser(description='Analyze pupil tracking data')
    parser.add_argument(
        'recording_path',
        nargs='?',
        default=DEFAULT_RECORDING_PATH,
        help='Path to pupil_positions.csv file (default: %(default)s)'
    )
    args = parser.parse_args()

    main(args.recording_path)