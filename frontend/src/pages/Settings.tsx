import { useState, useEffect } from 'react';
import { getSettings, saveSettings, resetPersonalBaseline } from '../services/api';

export default function Settings() {
  const [loading, setLoading] = useState(true);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  const [automation, setAutomation] = useState(true);
  const [cameraSensing, setCameraSensing] = useState(true);
  const [demoMode, setDemoMode] = useState(false);
  const [cycleMinutes, setCycleMinutes] = useState(5);
  const [demoCycleMinutes, setDemoCycleMinutes] = useState(1);

  // Personalization settings
  const [personalization, setPersonalization] = useState(true);
  const [calibrationCycles, setCalibrationCycles] = useState(5);
  const [adaptationSpeed, setAdaptationSpeed] = useState('Normal');

  const [sensitivity, setSensitivity] = useState('ultra_responsive');
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Advanced thresholds
  const [thWorkload, setThWorkload] = useState(0.40);
  const [thFrustration, setThFrustration] = useState(0.25);
  const [thFatigue, setThFatigue] = useState(0.25);
  const [thBackspace, setThBackspace] = useState(0.08);

  useEffect(() => {
    getSettings()
      .then((cfg) => {
        if (cfg) {
          setAutomation(cfg.automation_enabled ?? true);
          setCameraSensing(cfg.camera_sensing_enabled ?? true);
          setDemoMode(cfg.demo_mode ?? false);
          setCycleMinutes(cfg.cycle_duration_minutes ?? 5);
          setDemoCycleMinutes(cfg.demo_cycle_minutes ?? 1);
          setPersonalization(cfg.personalization_enabled ?? true);
          setCalibrationCycles(cfg.calibration_cycles ?? 5);
          setAdaptationSpeed(cfg.baseline_adaptation ?? 'Normal');
          setSensitivity(cfg.sensitivity ?? 'ultra_responsive');

          if (cfg.thresholds) {
            setThWorkload(cfg.thresholds.workload_high ?? 0.40);
            setThFrustration(cfg.thresholds.frustration_high ?? 0.25);
            setThFatigue(cfg.thresholds.fatigue_high ?? 0.25);
            setThBackspace(cfg.thresholds.typing_error_high ?? 0.08);
          }
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    try {
      await saveSettings({
        automation_enabled: automation,
        camera_sensing_enabled: cameraSensing,
        demo_mode: demoMode,
        cycle_duration_minutes: Number(cycleMinutes),
        demo_cycle_minutes: Number(demoCycleMinutes),
        personalization_enabled: personalization,
        calibration_cycles: Number(calibrationCycles),
        baseline_adaptation: adaptationSpeed,
        sensitivity,
        thresholds: {
          workload_high: Number(thWorkload),
          frustration_high: Number(thFrustration),
          fatigue_high: Number(thFatigue),
          typing_error_high: Number(thBackspace),
        }
      });
      setSaveMsg('Settings saved successfully and applied to active 5-minute cycle.');
      setTimeout(() => setSaveMsg(null), 3500);
    } catch (err: any) {
      setSaveMsg(`Error saving settings: ${err.message}`);
      setTimeout(() => setSaveMsg(null), 4000);
    }
  };

  const handleResetBaseline = async () => {
    try {
      const res = await resetPersonalBaseline();
      setSaveMsg(res.message || 'Personal baseline reset to calibration mode.');
      setTimeout(() => setSaveMsg(null), 4000);
    } catch (err: any) {
      setSaveMsg(`Error resetting baseline: ${err.message}`);
      setTimeout(() => setSaveMsg(null), 4000);
    }
  };

  if (loading) {
    return (
      <div className="empty-state-box">
        <div className="empty-icon">⚙️</div>
        <h2>Loading Settings...</h2>
      </div>
    );
  }

  return (
    <div>
      <div className="pagehead">
        <div>
          <h1>System &amp; Personalization Settings</h1>
          <p>Configure the 5-minute adaptive cycle, personal learning baseline, and privacy controls.</p>
        </div>
        <button className="btn-primary" onClick={handleSave}>
          💾 Save &amp; Apply Settings
        </button>
      </div>

      {saveMsg && (
        <div className="toast-msg">
          <span>✓</span>
          <span>{saveMsg}</span>
        </div>
      )}

      {/* 5-Minute Cycle Interval Configuration */}
      <section className="card settings">
        <h2>Adaptive Cycle Timing</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 14 }}>
          EAOS evaluates your continuous work cadence and adapts the desktop environment at the end of each cycle.
        </p>

        <div className="twocol">
          <div className="form-group">
            <label>Standard Assessment Interval (Minutes):</label>
            <input
              type="number"
              min="1"
              max="60"
              value={cycleMinutes}
              onChange={(e) => setCycleMinutes(Number(e.target.value))}
            />
            <small style={{ color: 'var(--text-muted)', display: 'block', marginTop: 4 }}>
              Default: 5 minutes continuous cycle
            </small>
          </div>

          <div className="form-group">
            <label className="checkbox-row" style={{ border: 'none', padding: '0 0 8px 0' }}>
              <div>
                <b style={{ color: '#38bdf8' }}>Demo Mode (1-Minute Cycle)</b>
                <small style={{ display: 'block', color: 'var(--text-muted)' }}>
                  Compresses cycle to 1 minute for fast live demonstrations.
                </small>
              </div>
              <input
                type="checkbox"
                checked={demoMode}
                onChange={(e) => setDemoMode(e.target.checked)}
              />
            </label>
          </div>
        </div>
      </section>

      {/* Personalization Configuration */}
      <section className="card settings">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <h2>Personalization &amp; Learning Baseline</h2>
          <button
            className="btn-secondary"
            onClick={handleResetBaseline}
            title="Clear learned statistics and restart the 5-cycle calibration"
          >
            🔄 Reset Personal Baseline
          </button>
        </div>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 14 }}>
          Learns your personal typing speed, workload, and mouse dynamics to detect deviations from your normal habits rather than applying rigid one-size-fits-all rules.
        </p>

        <label className="checkbox-row">
          <div>
            <b>Enable Personalization</b>
            <small style={{ display: 'block', color: 'var(--text-muted)' }}>
              When enabled, EAOS compares each 5-minute window against your individual baseline.
            </small>
          </div>
          <input
            type="checkbox"
            checked={personalization}
            onChange={(e) => setPersonalization(e.target.checked)}
          />
        </label>

        <div className="twocol" style={{ marginTop: 14 }}>
          <div className="form-group">
            <label>Calibration Cycles (Initial Learning Period):</label>
            <input
              type="number"
              min="2"
              max="20"
              value={calibrationCycles}
              onChange={(e) => setCalibrationCycles(Number(e.target.value))}
            />
            <small style={{ color: 'var(--text-muted)', display: 'block', marginTop: 4 }}>
              Default: 5 cycles (25 minutes). Conservative adaptations during calibration.
            </small>
          </div>

          <div className="form-group">
            <label>Baseline Adaptation Speed (EWMA Alpha):</label>
            <select
              className="select-filter"
              value={adaptationSpeed}
              onChange={(e) => setAdaptationSpeed(e.target.value)}
            >
              <option value="Slow">Slow (Gradual long-term memory, α = 0.05)</option>
              <option value="Normal">Normal (Balanced, α = 0.10)</option>
              <option value="Fast">Fast (Responsive to recent days, α = 0.20)</option>
            </select>
          </div>
        </div>
      </section>

      {/* Camera Privacy Settings */}
      <section className="card settings">
        <h2>Camera Privacy &amp; Facial Sensing</h2>
        <label className="checkbox-row">
          <div>
            <b>Camera Sensing Integration</b>
            <small style={{ display: 'block', color: 'var(--text-muted)' }}>
              If disabled, the camera is never opened. EAOS adapts using only keyboard, mouse, active application, and workload signals.
            </small>
          </div>
          <input
            type="checkbox"
            checked={cameraSensing}
            onChange={(e) => setCameraSensing(e.target.checked)}
          />
        </label>

        <label className="checkbox-row">
          <div>
            <b>In-Memory Frame Processing</b>
            <small style={{ display: 'block', color: 'var(--text-muted)' }}>
              Frames are evaluated in RAM and immediately discarded. Raw images are never saved to disk.
            </small>
          </div>
          <input type="checkbox" defaultChecked disabled />
        </label>
      </section>

      {/* Autonomous Actions & Sensitivity */}
      <section className="card settings">
        <h2>Decision Engine &amp; Sensitivity</h2>
        <label className="checkbox-row" style={{ marginBottom: 16 }}>
          <div>
            <b>Automatic macOS Adaptations</b>
            <small style={{ display: 'block', color: 'var(--text-muted)' }}>
              Automatically executes Dark Mode, Focus Mode, or Break alerts at the end of each 5-minute cycle.
            </small>
          </div>
          <input
            type="checkbox"
            checked={automation}
            onChange={(e) => setAutomation(e.target.checked)}
          />
        </label>

        <div className="form-group">
          <label>Demonstration Sensitivity Preset:</label>
          <select
            className="select-filter"
            value={sensitivity}
            onChange={(e) => setSensitivity(e.target.value)}
          >
            <option value="ultra_responsive">Ultra Responsive (Recommended for presentations)</option>
            <option value="high">High Sensitivity</option>
            <option value="normal">Normal</option>
            <option value="low">Low (Conservative)</option>
          </select>
        </div>

        <div style={{ marginTop: 18 }}>
          <button
            className="btn-secondary"
            onClick={() => setShowAdvanced(!showAdvanced)}
          >
            {showAdvanced ? '▲ Hide Advanced Thresholds' : '▼ Show Advanced Thresholds'}
          </button>
        </div>

        {showAdvanced && (
          <div className="advanced-thresholds-box" style={{ marginTop: 16 }}>
            <h3>Demonstration Threshold Triggers</h3>
            <div className="twocol">
              <div className="form-group">
                <label>Workload High Trigger ({Math.round(thWorkload * 100)}%):</label>
                <input
                  type="number"
                  step="0.05"
                  min="0.1"
                  max="0.9"
                  value={thWorkload}
                  onChange={(e) => setThWorkload(Number(e.target.value))}
                />
              </div>

              <div className="form-group">
                <label>Frustration Trigger ({Math.round(thFrustration * 100)}%):</label>
                <input
                  type="number"
                  step="0.05"
                  min="0.1"
                  max="0.8"
                  value={thFrustration}
                  onChange={(e) => setThFrustration(Number(e.target.value))}
                />
              </div>

              <div className="form-group">
                <label>Fatigue Trigger ({Math.round(thFatigue * 100)}%):</label>
                <input
                  type="number"
                  step="0.05"
                  min="0.1"
                  max="0.8"
                  value={thFatigue}
                  onChange={(e) => setThFatigue(Number(e.target.value))}
                />
              </div>

              <div className="form-group">
                <label>Typing Error Trigger ({Math.round(thBackspace * 100)}%):</label>
                <input
                  type="number"
                  step="0.01"
                  min="0.02"
                  max="0.30"
                  value={thBackspace}
                  onChange={(e) => setThBackspace(Number(e.target.value))}
                />
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
