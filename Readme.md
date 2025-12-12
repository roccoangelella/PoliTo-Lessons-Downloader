# Polito Video Downloader

Downloads video lectures from the Polito portal. Includes an automated compression feature to keep files under 200MB (optimized for NotebookLM) by reducing video resolution while preserving audio quality.

## Requirements

1. Google Chrome
2. FFmpeg (Must be installed and added to your system PATH)

## Setup

Install the required Python libraries:

```bash
pip install selenium requests
```

#### Warning:
Downscaling with FFMPEG will destroy the video's quality, which is fine if you just want to feed it into NotebookLM.
