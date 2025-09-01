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
    filtered_df = filtered_df[filtered_df["eye_id"] != 1]
    return pupil_df, filtered_df


def create_visualizations(pupil_df, filtered_df, analysis_dir):
    """Create and save all visualizations to HTML files"""
    # Create analysis directory if it doesn't exist
    analysis_dir.mkdir(parents=True, exist_ok=True)

    # 1. Time Series Plot
    fig_time = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.02)
    fig_time.add_trace(go.Scatter(y=filtered_df["phi"], mode="lines+markers", name="phi"), row=1, col=1)
    fig_time.add_trace(go.Scatter(y=filtered_df["theta"], mode="lines+markers", name="theta"), row=2, col=1)
    fig_time.update_layout(height=800, width=1280, title_text="Pupil Positions Time Series")
    time_series_path = analysis_dir / "time_series.html"
    fig_time.write_html(str(time_series_path))


    return [time_series_path]


def main(recording_path):
    pupil_path = Path(recording_path)
    analysis_dir = pupil_path.parent / "analysis"
    analysis_dir.mkdir(exist_ok=True, parents=True)
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
    RECORDING_PATH = r"C:\Users\jonma\recordings\2025_03_10\001\exports\000\pupil_positions.csv"


    main(RECORDING_PATH)