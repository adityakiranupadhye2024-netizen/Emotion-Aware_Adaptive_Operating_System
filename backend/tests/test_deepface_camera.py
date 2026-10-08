#!/usr/bin/env python3
"""
Manual standalone test utility for real Mac camera -> face detection -> DeepFace emotion recognition.
Verifies the complete vision inference pipeline locally and releases hardware cleanly.
"""
import sys
import time
import cv2
import numpy as np

try:
    from deepface import DeepFace
except ImportError:
    print("ERROR: deepface is not installed in the active environment.")
    sys.exit(1)


def main():
    print("==================================================")
    print("EAOS Mac Camera -> DeepFace Emotion Pipeline Test")
    print("==================================================")
    print("1. Opening camera hardware (index 0)...")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Failed to open camera hardware (index 0).")
        print("Please check camera permissions in System Settings -> Privacy & Security -> Camera.")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # Let camera sensor warm up and adjust exposure for a few frames
    print("   Camera opened. Warming up sensor...")
    warmup_frames = 10
    frame = None
    for _ in range(warmup_frames):
        ok, f = cap.read()
        if ok and f is not None:
            frame = f
        time.sleep(0.05)

    if frame is None:
        print("ERROR: Could not read a valid frame from camera.")
        cap.release()
        sys.exit(1)

    h, w = frame.shape[:2]
    print(f"   Captured frame: {w}x{h}")

    print("2. Running OpenCV Face Detection...")
    hdir = cv2.data.haarcascades
    face_cascade = cv2.CascadeClassifier(hdir + 'haarcascade_frontalface_alt2.xml')
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(40, 40))

    face_detected = len(faces) > 0
    crop_target = frame
    face_box = None

    if face_detected:
        # Select largest face
        best_face = max(faces, key=lambda f: f[2] * f[3])
        fx, fy, fw, fh = best_face
        face_box = (fx, fy, fw, fh)
        print(f"   Face DETECTED: box=(x={fx}, y={fy}, w={fw}, h={fh}), area={fw*fh}px")
        # Pad bounding box
        pad_x = int(fw * 0.15)
        pad_y = int(fh * 0.15)
        x1 = max(0, fx - pad_x)
        y1 = max(0, fy - pad_y)
        x2 = min(w, fx + fw + pad_x)
        y2 = min(h, fy + fh + pad_y)
        crop_target = frame[y1:y2, x1:x2]
        quality_score = min(0.99, max(0.50, (fw * fh) / (120.0 * 120.0) * 0.90))
    else:
        print("   Face NOT detected via Haar cascade. Analyzing full frame with DeepFace detector...")
        quality_score = 0.35

    print("3. Running DeepFace Emotion Analysis...")
    t0 = time.time()
    try:
        backend = "skip" if face_detected else "opencv"
        analysis = DeepFace.analyze(
            img_path=crop_target,
            actions=['emotion'],
            enforce_detection=False,
            detector_backend=backend
        )
        duration_ms = (time.time() - t0) * 1000
    except Exception as e:
        print(f"ERROR: DeepFace analysis failed: {e}")
        cap.release()
        sys.exit(1)

    result = analysis[0] if isinstance(analysis, list) and len(analysis) > 0 else analysis
    raw_emotions = result.get('emotion', {})
    dominant = result.get('dominant_emotion', 'unknown')

    # Convert to normalized [0.0 - 1.0] probabilities
    floats = {k: max(0.0, float(v)) for k, v in raw_emotions.items()}
    total = sum(floats.values())
    if total > 0:
        normalized = {k: round(v / total, 4) for k, v in floats.items()}
    else:
        normalized = {k: round(1.0 / len(floats), 4) for k in floats}

    print("==================================================")
    print("RESULTS:")
    print("==================================================")
    print(f"Inference Time:      {duration_ms:.1f} ms")
    print(f"Face Detected:       {'YES' if face_detected else 'NO'}")
    print(f"Face Box:            {face_box if face_box else 'N/A'}")
    print(f"Detection Quality:   {quality_score:.2f}")
    print(f"Dominant Emotion:    {dominant.upper()}")
    print("Emotion Probabilities (normalized [0, 1]):")
    for emo, prob in sorted(normalized.items(), key=lambda x: x[1], reverse=True):
        bar = "█" * int(prob * 30)
        print(f"  - {emo:<10}: {prob:.4f} ({prob*100:5.1f}%) {bar}")

    print("==================================================")
    print("4. Releasing camera hardware safely...")
    cap.release()
    print("Camera hardware released cleanly. Test passed.")
    print("==================================================")


if __name__ == '__main__':
    main()
