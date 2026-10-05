import React, { useState, useEffect, useRef } from 'react';
import { getCameraStreamUrl, setCameraPreview } from '../services/api';

interface CameraBoxProps {
  emotion?: {
    dominant?: string;
    confidence?: number;
    probabilities?: Record<string, number>;
  };
  cameraState?: {
    active?: boolean;
    status?: string;
    face_detected?: boolean;
    eyes_detected?: boolean;
    smile_detected?: boolean;
    confidence?: number;
    ambient_light?: number;
    lighting_condition?: string;
    fatigue_score?: number;
  };
  cycle?: {
    phase?: string;
    remaining_seconds?: number;
  };
}

export const CameraBox: React.FC<CameraBoxProps> = ({
  emotion,
  cameraState,
  cycle
}) => {
  const [isPreviewActive, setIsPreviewActive] = useState<boolean>(false);
  const [useBrowserCam, setUseBrowserCam] = useState<boolean>(false);
  const [browserCamError, setBrowserCamError] = useState<string | null>(null);
  const [streamKey, setStreamKey] = useState<number>(Date.now());
  const [loadingToggle, setLoadingToggle] = useState<boolean>(false);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const dominantEmotion = emotion?.dominant || 'Focused';
  const emotionConfidence = emotion?.confidence ?? (cameraState?.confidence || 0.85);
  const faceDetected = cameraState?.face_detected ?? true;
  const isInputPhase = cycle?.phase === 'INPUT_COLLECTION';

  // Dynamic emotion palette
  const emotionThemes: Record<string, { bg: string; text: string; border: string; icon: string; glow: string }> = {
    Focused: {
      bg: 'rgba(56, 189, 248, 0.2)',
      text: '#38bdf8',
      border: 'rgba(56, 189, 248, 0.5)',
      icon: '🎯',
      glow: '0 0 15px rgba(56, 189, 248, 0.4)'
    },
    'Flow State': {
      bg: 'rgba(168, 85, 247, 0.2)',
      text: '#c084fc',
      border: 'rgba(168, 85, 247, 0.5)',
      icon: '⚡',
      glow: '0 0 15px rgba(168, 85, 247, 0.4)'
    },
    Relaxed: {
      bg: 'rgba(52, 211, 153, 0.2)',
      text: '#34d399',
      border: 'rgba(52, 211, 153, 0.5)',
      icon: '😌',
      glow: '0 0 15px rgba(52, 211, 153, 0.4)'
    },
    Fatigued: {
      bg: 'rgba(251, 191, 36, 0.2)',
      text: '#fbbf24',
      border: 'rgba(251, 191, 36, 0.5)',
      icon: '🥱',
      glow: '0 0 15px rgba(251, 191, 36, 0.4)'
    },
    Frustrated: {
      bg: 'rgba(248, 113, 113, 0.2)',
      text: '#f87171',
      border: 'rgba(248, 113, 113, 0.5)',
      icon: '😤',
      glow: '0 0 15px rgba(248, 113, 113, 0.4)'
    },
    Confused: {
      bg: 'rgba(253, 224, 71, 0.2)',
      text: '#fde047',
      border: 'rgba(253, 224, 71, 0.5)',
      icon: '🤔',
      glow: '0 0 15px rgba(253, 224, 71, 0.4)'
    }
  };

  const theme = emotionThemes[dominantEmotion] || emotionThemes['Focused'];

  // Toggle backend preview
  const handleTogglePreview = async () => {
    setLoadingToggle(true);
    try {
      const next = !isPreviewActive;
      await setCameraPreview(next);
      setIsPreviewActive(next);
      setStreamKey(Date.now());
    } catch (err) {
      console.error('Failed to toggle preview:', err);
    } finally {
      setLoadingToggle(false);
    }
  };

  // Browser WebCam handling
  useEffect(() => {
    if (useBrowserCam) {
      navigator.mediaDevices?.getUserMedia({ video: { width: 640, height: 480 } })
        .then((s) => {
          streamRef.current = s;
          if (videoRef.current) {
            videoRef.current.srcObject = s;
            videoRef.current.play();
          }
          setBrowserCamError(null);
        })
        .catch((err) => {
          console.warn('Browser webcam error:', err);
          setBrowserCamError('Browser webcam blocked or unavailable. Switching back to backend stream.');
          setUseBrowserCam(false);
        });
    } else {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
    }
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
      }
    };
  }, [useBrowserCam]);

  // Clean-up backend preview on unmount
  useEffect(() => {
    return () => {
      setCameraPreview(false).catch(() => {});
    };
  }, []);

  return (
    <div
      className="card eaos-camera-box"
      style={{
        background: 'linear-gradient(145deg, rgba(15, 23, 42, 0.95) 0%, rgba(30, 41, 59, 0.88) 100%)',
        border: `1px solid ${theme.border}`,
        borderRadius: '14px',
        padding: '18px 20px',
        marginBottom: '20px',
        boxShadow: `0 8px 32px rgba(0, 0, 0, 0.35), ${theme.glow}`,
        position: 'relative',
        overflow: 'hidden',
        transition: 'all 0.3s ease'
      }}
    >
      {/* Header bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10, marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: '1.4rem' }}>👁️</span>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700, color: '#f8fafc', letterSpacing: '-0.01em' }}>
                AI Vision &amp; Facial Emotion Tracking
              </h3>
              <span style={{
                fontSize: '0.72rem',
                padding: '2px 8px',
                borderRadius: 20,
                background: (isInputPhase || isPreviewActive || cameraState?.active) ? 'rgba(52, 211, 153, 0.2)' : 'rgba(148, 163, 184, 0.15)',
                color: (isInputPhase || isPreviewActive || cameraState?.active) ? '#34d399' : '#94a3b8',
                border: `1px solid ${(isInputPhase || isPreviewActive || cameraState?.active) ? 'rgba(52, 211, 153, 0.4)' : 'rgba(148, 163, 184, 0.25)'}`,
                fontWeight: 600
              }}>
                {(isInputPhase || isPreviewActive || cameraState?.active) ? '● ACTIVE SENSING' : '○ STANDBY'}
              </span>
            </div>
            <p style={{ margin: '3px 0 0', fontSize: '0.8rem', color: '#94a3b8' }}>
              Real-time on-device facial valence, smile detection, and emotion classification with HUD overlay
            </p>
          </div>
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            onClick={() => setUseBrowserCam(!useBrowserCam)}
            className="btn btn-sm"
            style={{
              background: useBrowserCam ? 'rgba(168, 85, 247, 0.25)' : 'rgba(255, 255, 255, 0.06)',
              border: `1px solid ${useBrowserCam ? '#a855f7' : 'rgba(255, 255, 255, 0.15)'}`,
              color: '#f8fafc',
              fontSize: '0.75rem',
              padding: '5px 12px',
              borderRadius: 6,
              cursor: 'pointer'
            }}
            title="Switch between Backend OpenCV Stream and Direct Browser WebCam"
          >
            {useBrowserCam ? '📷 Browser Cam' : '🖥️ OpenCV Stream'}
          </button>

          {!useBrowserCam && (
            <button
              onClick={handleTogglePreview}
              disabled={loadingToggle}
              className="btn btn-sm"
              style={{
                background: isPreviewActive ? 'rgba(239, 68, 68, 0.25)' : 'rgba(56, 189, 248, 0.2)',
                border: `1px solid ${isPreviewActive ? '#ef4444' : 'rgba(56, 189, 248, 0.4)'}`,
                color: isPreviewActive ? '#fca5a5' : '#38bdf8',
                fontSize: '0.75rem',
                padding: '5px 12px',
                borderRadius: 6,
                fontWeight: 600,
                cursor: loadingToggle ? 'wait' : 'pointer'
              }}
            >
              {loadingToggle ? 'Updating...' : isPreviewActive ? '⏹ Stop Live Cam' : '▶ Live Cam Preview'}
            </button>
          )}

          <button
            onClick={() => setStreamKey(Date.now())}
            className="btn btn-sm"
            style={{
              background: 'rgba(255, 255, 255, 0.06)',
              border: '1px solid rgba(255, 255, 255, 0.12)',
              color: '#cbd5e1',
              fontSize: '0.75rem',
              padding: '5px 8px',
              borderRadius: 6,
              cursor: 'pointer'
            }}
            title="Refresh stream connection"
          >
            🔄
          </button>
        </div>
      </div>

      {browserCamError && (
        <div style={{
          padding: '8px 12px',
          background: 'rgba(239, 68, 68, 0.15)',
          border: '1px solid rgba(239, 68, 68, 0.3)',
          borderRadius: 6,
          color: '#fca5a5',
          fontSize: '0.78rem',
          marginBottom: 12
        }}>
          ⚠️ {browserCamError}
        </div>
      )}

      {/* Main Viewport Container */}
      <div
        style={{
          position: 'relative',
          width: '100%',
          maxWidth: '720px',
          margin: '0 auto',
          height: '380px',
          borderRadius: '10px',
          overflow: 'hidden',
          background: '#090d16',
          border: '1px solid rgba(56, 189, 248, 0.25)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: 'inset 0 0 40px rgba(0, 0, 0, 0.8)'
        }}
      >
        {/* Video / Stream View */}
        {useBrowserCam ? (
          <div style={{ width: '100%', height: '100%', position: 'relative' }}>
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                transform: 'scaleX(-1)' // Mirror view for natural interaction
              }}
            />
            <canvas
              ref={canvasRef}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                height: '100%',
                pointerEvents: 'none'
              }}
            />
          </div>
        ) : (
          <img
            key={streamKey}
            src={`${getCameraStreamUrl()}?t=${streamKey}`}
            alt="EAOS Live Face & Emotion Stream"
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover'
            }}
            onError={(e) => {
              // Retry on transient network blip
              setTimeout(() => {
                setStreamKey(Date.now());
              }, 2000);
            }}
          />
        )}

        {/* Floating HUD Emotion Badge (In Camera Display) */}
        <div
          style={{
            position: 'absolute',
            top: '16px',
            left: '16px',
            background: 'rgba(15, 23, 42, 0.88)',
            backdropFilter: 'blur(8px)',
            border: `1.5px solid ${theme.border}`,
            borderRadius: '8px',
            padding: '8px 14px',
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            boxShadow: `0 4px 20px rgba(0,0,0,0.5), ${theme.glow}`,
            zIndex: 10
          }}
        >
          <span style={{ fontSize: '1.3rem' }}>{theme.icon}</span>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: '0.72rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Detected Emotion
              </span>
              <span style={{
                fontSize: '0.68rem',
                color: theme.text,
                background: theme.bg,
                padding: '1px 6px',
                borderRadius: 4,
                fontWeight: 700
              }}>
                {Math.round(emotionConfidence * 100)}% Match
              </span>
            </div>
            <div style={{ fontSize: '1.05rem', fontWeight: 800, color: theme.text, letterSpacing: '-0.01em' }}>
              {dominantEmotion.toUpperCase()}
            </div>
          </div>
        </div>

        {/* Biometrics & Facial Feature Pills in Camera */}
        <div
          style={{
            position: 'absolute',
            bottom: '16px',
            left: '16px',
            right: '16px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 8,
            zIndex: 10
          }}
        >
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <span style={{
              fontSize: '0.74rem',
              padding: '4px 10px',
              borderRadius: 6,
              background: 'rgba(15, 23, 42, 0.85)',
              border: `1px solid ${faceDetected ? 'rgba(52, 211, 153, 0.4)' : 'rgba(251, 191, 36, 0.4)'}`,
              color: faceDetected ? '#34d399' : '#fbbf24',
              fontWeight: 600,
              backdropFilter: 'blur(6px)'
            }}>
              {faceDetected ? '● Face Tracked' : '○ Searching Face'}
            </span>

            <span style={{
              fontSize: '0.74rem',
              padding: '4px 10px',
              borderRadius: 6,
              background: 'rgba(15, 23, 42, 0.85)',
              border: `1px solid ${cameraState?.eyes_detected ? 'rgba(56, 189, 248, 0.4)' : 'rgba(148, 163, 184, 0.3)'}`,
              color: cameraState?.eyes_detected ? '#38bdf8' : '#cbd5e1',
              fontWeight: 600,
              backdropFilter: 'blur(6px)'
            }}>
              {cameraState?.eyes_detected ? '👀 Eyes Engaged' : '😑 Eye Tracking'}
            </span>

            {cameraState?.smile_detected && (
              <span style={{
                fontSize: '0.74rem',
                padding: '4px 10px',
                borderRadius: 6,
                background: 'rgba(15, 23, 42, 0.85)',
                border: '1px solid rgba(52, 211, 153, 0.4)',
                color: '#34d399',
                fontWeight: 600,
                backdropFilter: 'blur(6px)'
              }}>
                😊 Smile Detected
              </span>
            )}
          </div>

          <span style={{
            fontSize: '0.72rem',
            padding: '4px 10px',
            borderRadius: 6,
            background: 'rgba(15, 23, 42, 0.85)',
            border: '1px solid rgba(255, 255, 255, 0.15)',
            color: '#94a3b8',
            backdropFilter: 'blur(6px)'
          }}>
            🔆 Ambient Light: {cameraState?.lighting_condition || 'NORMAL'} ({cameraState?.ambient_light ?? 0.5})
          </span>
        </div>

        {/* Cyber Scanning Line Animation Overlay */}
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: '2px',
            background: 'linear-gradient(90deg, transparent 0%, rgba(56, 189, 248, 0.7) 50%, transparent 100%)',
            boxShadow: '0 0 10px #38bdf8',
            animation: 'eaos-scanline 4s linear infinite',
            pointerEvents: 'none'
          }}
        />
      </div>

      {/* Footer Info & Privacy Guarantee */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12, fontSize: '0.75rem', color: '#94a3b8', flexWrap: 'wrap', gap: 6 }}>
        <span>
          🔒 <b>100% On-Device Local Inference:</b> Video is processed in RAM and never written to disk or sent to the cloud.
        </span>
        <span>
          {isInputPhase
            ? '📥 Current cycle is accumulating facial data for next adaptation.'
            : isPreviewActive
            ? '⚡ Live camera preview active on demand.'
            : '🛡️ Camera hardware automatically stands by outside the 1-min sensing window to preserve privacy.'}
        </span>
      </div>
    </div>
  );
};
