"""
One-time setup: downloads the MediaPipe Face Landmarker model asset used by
app/ai/facial_emotion.py. Run once after installing requirements.txt:

    python scripts/download_models.py

Requires internet access to Google's public MediaPipe model bucket (this is
the official, documented distribution URL from Google's MediaPipe Tasks
docs — not a synthesized link). The file is ~4-6 MB.

If the user's environment blocks that host, they can instead download the
file manually from the same URL on any machine and copy it to
`backend/app/ai/models/face_landmarker.task`.
"""

import os
import sys
import urllib.request

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/latest/face_landmarker.task"
)

DEST_DIR = os.path.join(os.path.dirname(__file__), "..", "app", "ai", "models")
DEST_PATH = os.path.join(DEST_DIR, "face_landmarker.task")


def main() -> None:
    os.makedirs(DEST_DIR, exist_ok=True)

    if os.path.isfile(DEST_PATH) and os.path.getsize(DEST_PATH) > 0:
        print(f"Model already present at {DEST_PATH}, skipping download.")
        return

    print(f"Downloading face_landmarker.task from {MODEL_URL} ...")
    try:
        urllib.request.urlretrieve(MODEL_URL, DEST_PATH)
    except Exception as exc:
        print(f"Download failed: {exc}", file=sys.stderr)
        print(
            "If this network cannot reach storage.googleapis.com, download "
            f"the file manually from:\n  {MODEL_URL}\n"
            f"and place it at:\n  {os.path.abspath(DEST_PATH)}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Saved model to {os.path.abspath(DEST_PATH)} ({os.path.getsize(DEST_PATH)} bytes)")


if __name__ == "__main__":
    main()
