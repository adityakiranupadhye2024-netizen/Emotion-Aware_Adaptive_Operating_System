# macOS Setup & Configuration Guide — EAOS

This guide covers complete setup instructions for running the **Emotion-Aware Adaptive Operating System (EAOS)** natively on macOS (Apple Silicon M1/M2/M3/M4 or Intel).

---

## 1. System Requirements

* **Operating System**: macOS Monterey (12.0) or later (macOS Sonoma / Sequoia tested)
* **Python**: Python 3.10, 3.11, or 3.12
* **Node.js**: Node.js 18.x or 20.x LTS + `npm`
* **Hardware**: Built-in FaceTime HD Camera or external USB webcam

---

## 2. Setting Up macOS Native Shortcuts

EAOS uses the macOS command-line utility `shortcuts` to trigger system adaptations cleanly and natively without fragile GUI scripting. You must ensure the following 4 Shortcuts exist in your macOS **Shortcuts** app:

### Shortcut 1: `Set Appearance`
* **Open**: The **Shortcuts** app on macOS (press `Cmd + Space`, type `Shortcuts`).
* Click **+** (New Shortcut).
* Name the shortcut exactly: **`Set Appearance`**
* Add action: **Set Appearance** (search for "Set Appearance" in the action search bar).
* Configure: Set Appearance to **Ask Each Time** or pass Shortcut Input as Appearance.
* Alternatively, add an **If** block:
  * If `Shortcut Input` is `Dark` ➔ Set Appearance to **Dark**.
  * If `Shortcut Input` is `Light` ➔ Set Appearance to **Light**.
* Test in Terminal:
  ```bash
  shortcuts run "Set Appearance" <<< "Dark"
  shortcuts run "Set Appearance" <<< "Light"
  ```

### Shortcut 2: `Turn On DND`
* Create a new Shortcut named: **`Turn On DND`**
* Add action: **Set Focus** (search for "Set Focus").
* Add an **If** block:
  * If `Shortcut Input` is `On` ➔ Turn **Do Not Disturb** On until Turned Off.
  * If `Shortcut Input` is `Off` ➔ Turn **Do Not Disturb** Off.
* Test in Terminal:
  ```bash
  shortcuts run "Turn On DND" <<< "On"
  shortcuts run "Turn On DND" <<< "Off"
  ```

### Shortcut 3: `Set Volume`
* Create a new Shortcut named: **`Set Volume`**
* Add action: **Set Volume**.
* Configure volume level to accept **`Shortcut Input`** (as a percentage 0–100).
* Test in Terminal:
  ```bash
  shortcuts run "Set Volume" <<< "50"
  ```

### Shortcut 4: `Set Brightness`
* Create a new Shortcut named: **`Set Brightness`**
* Add action: **Set Brightness**.
* Configure brightness level to accept **`Shortcut Input`** (as a decimal e.g. `0.65`).
* Test in Terminal:
  ```bash
  shortcuts run "Set Brightness" <<< "0.65"
  ```

---

## 3. macOS Privacy & System Permissions

To capture behavioral signals (keyboard typing cadence, mouse dynamics, active application context, and camera sensing), macOS requires explicit user permissions for the terminal application you use (Terminal, iTerm2, or VS Code):

### A. Accessibility
* Open **System Settings > Privacy & Security > Accessibility**.
* Click **+** and add your terminal application (e.g., **Terminal**, **iTerm2**, or **Visual Studio Code**).
* Ensure the toggle is switched **ON**.
* *Purpose*: Allows EAOS to identify the active window application and mouse movement without administrative rights.

### B. Input Monitoring
* Open **System Settings > Privacy & Security > Input Monitoring**.
* Ensure your terminal application is enabled.
* *Purpose*: Measures typing cadence (inter-key timings and backspace frequency). **Typed characters and passwords are never logged or read**.

### C. Camera Access
* Open **System Settings > Privacy & Security > Camera**.
* When starting the backend for the first time, macOS will display an alert:
  > *"Terminal would like to access the camera."*
* Click **Allow**.
* *Purpose*: Enables the 1-minute in-memory facial engagement sensing window. Camera frames are processed strictly in RAM and are never stored on disk.

---

## 4. Backend Setup (FastAPI & OpenCV)

1. Open your terminal and navigate to the project directory:
   ```bash
   cd /path/to/eaos-full-project/backend
   ```

2. Create and activate a Python virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install required Python packages:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. Verify OpenCV and dependencies:
   ```bash
   python3 -c "import cv2, fastapi, pynput; print('Dependencies verified!')"
   ```

5. Launch the backend server:
   ```bash
   uvicorn app.main:app --port 8765 --host 127.0.0.1
   ```
   * The backend will output startup logs indicating SQLite database initialization, baseline loading, and wall-clock scheduler launch.

---

## 5. Frontend Dashboard Setup (React + Vite)

1. In a second terminal window, navigate to the `frontend` folder:
   ```bash
   cd /path/to/eaos-full-project/frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Launch the Vite dev server:
   ```bash
   npm run dev
   ```

4. Open your browser and navigate to:
   ```text
   http://127.0.0.1:5173
   ```

---

## 6. Verifying the System

1. **Check Live Telemetry**: Once the dashboard loads, verify the **`● EAOS ACTIVE`** and **`LIVE SYSTEM`** pills appear in the top header.
2. **Test AI Vision Box**: On the **Overview** page, observe the **AI Vision & Facial Emotion Tracking** card. Click **`▶ Live Cam Preview`** to verify your face is tracked with bounding box corner brackets and the real-time emotion badge is displayed.
3. **Test Actuator Shortcuts**: In the **Real OS Actuator & Mode Switcher** card on the Overview page, click **🌙 Dark Mode** or **☀️ Light Mode**. Verify that your macOS system appearance changes immediately and displays `✓ Verified on macOS hardware`.
4. **Test Reset**: Click **`🔄 Reset Adaptations`** in the header to verify that all 4 shortcuts run and restore baseline appearance, un-mute audio, and reset focus mode.

---

## 7. Troubleshooting

* **Port 8765 already in use**:
  ```bash
  lsof -ti :8765 | xargs kill -9
  ```
* **Camera shows "Hardware Released" or "Camera in Standby"**:
  * This is normal behavior during the 4-minute adaptation phase. Click **`▶ Live Cam Preview`** on the dashboard to view the camera stream on demand.
* **OpenCV VideoCapture Error**:
  * Ensure no other application (FaceTime, Photo Booth, Zoom) is holding an exclusive lock on the camera device.
* **Shortcut not found error**:
  * Ensure the Shortcut names match the exact spelling: `Set Appearance`, `Turn On DND`, `Set Volume`, and `Set Brightness`.
