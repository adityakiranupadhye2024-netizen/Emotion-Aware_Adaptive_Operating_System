export interface CycleStatus {
  cycle_id: number;
  phase: 'INPUT_COLLECTION' | 'PROCESSING' | 'SCORING' | 'DECIDING' | 'ACTUATING' | 'NOTIFYING' | string;
  mode: 'PRODUCTION' | 'DEMO' | 'SIMULATION' | string;
  cycle_duration_seconds: number;
  remaining_seconds: number;
  elapsed_seconds: number;
  next_processing_time: string;
  input_collection_active: boolean;
  decision_processing: boolean;
  camera_active: boolean;
  camera_status: string;
  camera_sensing_enabled: boolean;
  automation_enabled: boolean;
  personalization_status?: string;
  personalization_samples?: number;
  latest_decision?: any;
  latest_execution?: any;
}

export interface AdaptiveScore {
  score: number;
  emotion_component: number;
  context_component: number;
  workload_component: number;
  personalization_component: number;
  weights: Record<string, number>;
}

export interface PersonalizationInfo {
  status: 'CALIBRATING' | 'LEARNING' | 'ACTIVE' | 'DISABLED' | string;
  enabled: boolean;
  samples: number;
  calibration_cycles: number;
  baseline: Record<string, {
    mean: number;
    variance: number;
    std: number;
    observations: number;
  }>;
  deviations?: {
    workload?: { current: number; baseline: number; deviation: number; z_score: number };
    typing_rate?: { current: number; baseline: number; deviation: number; z_score: number };
    mouse_jitter?: { current: number; baseline: number; deviation: number; z_score: number };
  };
}

export interface LiveState {
  timestamp: string;
  mode: string;
  cycle: CycleStatus;
  cycle_id?: number;
  phase?: string;
  cycle_duration_seconds?: number;
  remaining_seconds?: number;
  next_processing_time?: string;
  input_collection_active?: boolean;
  decision_processing?: boolean;
  camera_active?: boolean;
  camera_status?: string;
  latest_action?: string;
  emotion: {
    dominant: string;
    probabilities: Record<string, number>;
    confidence: number;
  };
  context: {
    active_app: string;
    window_title: string;
    activity: string;
    session_duration: number;
    app_switch_rate: number;
    calendar_state: string;
    system_load?: {
      cpu: number;
      memory: number;
      processes: number;
    };
  };
  workload: {
    score: number;
    level: string;
    components: Record<string, number>;
  };
  personalization: PersonalizationInfo;
  adaptive_score: AdaptiveScore;
  ass?: AdaptiveScore;
  decision: {
    id?: number;
    action: string;
    reason: string;
    confidence: number;
    policy: string;
    status: string;
    adaptive_score?: number;
    personalization_summary?: string;
    timestamp?: string;
    message?: string;
    command_used?: string;
    verified?: boolean | number;
    execution_details?: any;
  };
  monitoring_paused?: boolean;
  heartbeats?: {
    last_keyboard_sec: number | null;
    last_mouse_sec: number | null;
    last_context_sec: number | null;
    last_camera_sec: number | null;
    keyboard_status: 'ACTIVE' | 'IDLE' | 'STALE' | string;
    mouse_status: 'ACTIVE' | 'IDLE' | 'STALE' | string;
    context_status: 'ACTIVE' | 'STALE' | string;
    camera_status: string;
  };
  policy?: {
    status: 'BASELINE' | 'LEARNING' | 'ADAPTIVE' | string;
    total_feedback_count: number;
    algorithm: string;
    supported_actions: string[];
  };
  inputs: {
    camera: {
      active: boolean;
      status?: string;
      face_detected: boolean;
      confidence: number;
      ambient_light?: number;
    };
    keyboard: {
      active: boolean;
      events: number;
      avg_inter_key_interval: number;
      typing_rate: number;
      backspace_rate: number;
    };
    mouse: {
      active: boolean;
      movement_distance: number;
      clicks: number;
      jitter?: number;
      idle: boolean;
    };
    active_app: string;
  };
  actual_os_state?: ActualOSState;
  system: {
    backend: string;
    decision_engine: string;
    os_adapter: string;
    scheduler: string;
    camera_status: string;
    monitoring_paused?: boolean;
  };
}

export interface ActualOSState {
  platform: string;
  actuator_ready: boolean;
  dark_mode: boolean;
  dark_mode_display: string;
  brightness: number;
  brightness_pct: number;
  brightness_controllable: boolean;
  volume?: number;
  volume_pct?: number;
  audio_muted: boolean;
  focus_mode_active: boolean;
  permission_status: 'GRANTED' | 'REQUIRED' | string;
  last_checked: string;
}

export interface ActionResult {
  action: string;
  requested: boolean;
  executed: boolean;
  verified: boolean;
  success: boolean;
  status: 'executed' | 'already_in_desired_state' | 'failed' | 'permission_required' | 'unsupported' | 'no_action' | string;
  command_used: string;
  state_before?: any;
  state_after?: any;
  message: string;
  execution_duration_ms: number;
  timestamp: string;
  error?: string | null;
}

export interface DecisionExplanation {
  summary: string;
  contributing_factors: Array<{
    factor: string;
    weight_or_value: string | number;
    impact: string;
  }>;
  confidence_rationale: string;
  context_modifier_applied: string;
}

export interface DecisionRecord {
  id: number;
  timestamp: string;
  cycle_id?: number;
  emotion: string;
  emotion_confidence?: number;
  workload: number;
  adaptive_score: number;
  ass?: number;
  context: string;
  context_confidence?: number;
  explanation?: DecisionExplanation;
  action: string;
  reason: string;
  confidence: number;
  policy: string;
  status: string;
  notification_status?: string;
  feedback?: 'KEEP' | 'UNDO' | 'DISMISS' | string;
  effectiveness?: 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE' | string;
  observed_as_change?: number;
  observed_workload_change?: number;
  pre_as?: number;
  post_as?: number;
  pre_workload?: number;
  post_workload?: number;
  verified?: number | boolean;
  command_used?: string;
  state_before?: any;
  state_after?: any;
  execution_error?: string;
}


export interface CycleRecord {
  id: number;
  cycle_number: number;
  start_time: string;
  end_time?: string;
  phase: string;
  camera_used: number;
  samples_count: number;
  adaptive_score: number;
  action: string;
  reason: string;
  status: string;
}

export interface NotificationRecord {
  id: number;
  decision_id?: number;
  cycle_id?: number;
  timestamp: string;
  title: string;
  message: string;
  action: string;
  adaptive_score: number;
  status: string;
}

export interface OSEventRecord {
  id: number;
  timestamp: string;
  setting: string;
  state: string;
  source: string;
  adaptive_score: number;
  reason: string;
  cycle_id: number;
  duration_seconds: number;
}

export interface OSDurations {
  dark_mode_seconds: number;
  light_mode_seconds: number;
  total_monitored_seconds: number;
  focus_mode_seconds: number;
  focus_disabled_seconds: number;
  focus_activations: number;
  focus_deactivations: number;
  current_appearance: string;
  current_focus: string;
}

export interface CameraStats {
  camera_on_seconds: number;
  camera_sessions_count: number;
  last_session_time?: string | null;
  sessions: Array<{
    id: number;
    start_time: string;
    end_time: string;
    duration_seconds: number;
    status: string;
  }>;
}

export interface AnalyticsDecision extends DecisionRecord {
  typing_rate?: number;
  backspace_rate?: number;
  mouse_jitter?: number;
  camera_active?: number;
  emotion_probabilities?: Record<string, number>;
  baseline_workload?: number;
  baseline_typing?: number;
  baseline_jitter?: number;
}

export interface AnalyticsSummary {
  period: string;
  total_assessments: number;
  decisions: AnalyticsDecision[];
  os_durations: OSDurations;
  os_events: OSEventRecord[];
  camera_stats: CameraStats;
  action_frequency: Record<string, number>;
  emotion_distribution: Record<string, number>;
  personal_baselines: Record<string, { mean: number; variance: number; observations: number }>;
  overview: {
    adaptive_score: number;
    workload: number;
    typing_speed: number;
    avg_typing_speed: number;
    baseline_typing: number;
    typing_deviation_pct: number;
    baseline_workload: number;
    baseline_jitter: number;
    dominant_emotion: string;
    adaptations_count: number;
    camera_sessions_count: number;
  };
}

export interface ContextObservation {
  id: number;
  timestamp: string;
  active_app: string;
  context: string;
  confidence: number;
  session_duration: number;
}

export interface EffectivenessStats {
  total_evaluated: number;
  positive_count: number;
  neutral_count: number;
  negative_count: number;
  positive_pct: number;
  neutral_pct: number;
  negative_pct: number;
  most_effective_adaptation: string;
  least_effective_adaptation: string;
  recent_events: Array<{
    id: number;
    decision_id: number;
    action: string;
    pre_as: number;
    post_as: number;
    as_delta: number;
    pre_workload: number;
    post_workload: number;
    workload_delta: number;
    outcome: string;
    timestamp: string;
  }>;
}

export interface PolicyStatus {
  status: 'BASELINE' | 'LEARNING' | 'ADAPTIVE' | string;
  total_feedback_count: number;
  algorithm: string;
  supported_actions: string[];
  policy_stats?: {
    total_events: number;
    average_reward: number;
  };
}

export interface PrivacyStatus {
  monitoring_paused: boolean;
  camera_sensing_enabled: boolean;
  camera_hardware_state: 'ACTIVE' | 'OFF' | 'BLOCKED' | 'PAUSED' | string;
  camera_stats: CameraStats;
  raw_frames_stored: boolean;
  text_typed_stored: boolean;
  keystroke_content_zero_logging: boolean;
  local_processing_only: boolean;
  retention_setting: string;
}


