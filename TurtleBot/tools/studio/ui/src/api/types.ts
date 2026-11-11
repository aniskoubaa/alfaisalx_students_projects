/**
 * Types for every Studio endpoint and event. Source of truth for the UI side.
 * Written from web/app.js and web/mock.js (1.3) plus the 2.0 additions in studio-2.0-plan.md.
 * Fields the backend may omit are optional or nullable.
 */

/* ---------- results ---------- */

/** A failed call. `error` is always plain text a person can read. */
export interface ApiFailure {
  ok: false;
  error: string;
  /** Machine hint from Studio, for example 'key_not_set_up', 'host_key', 'no_ssh'. */
  kind?: string;
  /** HTTP status when the failure came from the network layer. */
  status?: number;
  /** Set when the call never got an answer (offline, timeout). */
  network?: boolean;
  needs_confirm?: boolean;
  needs_settings?: boolean;
  preview?: string;
  /** A map with that name already exists (mapping_save without overwrite). */
  exists?: boolean;
}

export type ApiOk<T> = { ok: true } & T;
export type ApiResult<T> = ApiOk<T> | ApiFailure;

/* ---------- connection ---------- */

export type ConnState =
  'disconnected' | 'discovering' | 'connecting' | 'connected' | 'reconnecting' | 'error';

export interface ConnEvent {
  ev: 'conn';
  state: ConnState;
  host?: string | null;
  via?: string | null;
  error?: string | null;
  kind?: string;
  attempt?: number;
  next_in?: number;
  since?: number;
}

export interface HelloEvent {
  ev: 'hello';
  version?: string;
  bridge?: string;
  hostname?: string;
  ros?: boolean;
  ros_distro?: string;
  rmw?: string;
  domain?: number;
  python?: string;
  pid?: number;
  fake?: boolean;
}

export interface Candidate {
  host: string;
  label?: string;
  via?: string;
  reachable: boolean;
  ms?: number | null;
  identity?: 'confirmed' | 'unknown' | string;
  pi?: boolean;
}

/* ---------- status snapshot (SSE 'status', about once a second) ---------- */

export interface BatteryStatus {
  percent?: number | null;
  voltage?: number | null;
  current_a?: number | null;
  charging?: boolean | null;
  full?: boolean | null;
}

export interface DockStatus {
  is_docked?: boolean | null;
  dock_visible?: boolean | null;
}

export interface OdomStatus {
  x?: number | null;
  y?: number | null;
  yaw_deg?: number | null;
  vx?: number | null;
  wz?: number | null;
  age_s?: number | null;
  rate_hz?: number | null;
}

export interface ScanStatus {
  rate_hz?: number | null;
  front_m?: number | null;
  min_m?: number | null;
  age_s?: number | null;
}

export interface EstopStatus {
  on: boolean | null;
  source?: string | null;
}

export interface SystemStatus {
  cpu_pct?: number | null;
  load1?: number | null;
  temp_c?: number | null;
  throttled?: string | null;
  mem_used_mb?: number | null;
  mem_total_mb?: number | null;
  disk_free_gb?: number | null;
  uptime_s?: number | null;
}

export interface NetStatus {
  wifi_mode?: string | null;
  ssid?: string | null;
  signal_dbm?: number | null;
  link_quality?: number | null;
  addresses?: Record<string, string>;
  powersave?: string | null;
  powersave_students?: string | null;
}

export interface ClockStatus {
  synced?: boolean | null;
  year?: number | null;
}

export interface RunSummary {
  run_id: string;
  name?: string;
  pid?: number | null;
  alive?: boolean;
  started_wall?: number;
  motion?: boolean;
}

export interface StatusEvent {
  ev: 'status';
  t?: number;
  wall?: number;
  battery?: BatteryStatus;
  dock?: DockStatus;
  odom?: OdomStatus;
  scan?: ScanStatus;
  hazards?: string[];
  estop?: EstopStatus;
  system?: SystemStatus;
  net?: NetStatus;
  clock?: ClockStatus;
  ros_service?: string | null;
  runs?: RunSummary[];
  /** 2.0: teleop state mirrored into the snapshot when the backend sends it. */
  teleop?: { armed: boolean } | null;
}

/* ---------- other events ---------- */

export interface DiscoverEvent {
  ev: 'discover';
  candidates?: Candidate[];
  deep?: boolean;
}
export interface DeepProgressEvent {
  ev: 'deep_progress';
  done: number;
  total: number;
}
export interface UpdateInfo {
  current?: string;
  latest?: string;
  newer?: boolean;
  page?: string;
  notes?: string;
  checked?: number;
  error?: string | null;
  dismissed?: string | null;
}
export type UpdateEvent = { ev: 'update' } & UpdateInfo;
export interface QuitEvent {
  ev: 'quit';
}
export interface SyncEvent {
  ev: 'sync';
  state: 'running' | 'done' | 'error' | 'preview';
  direction?: 'up' | 'down';
  uploaded?: string[];
  would_upload?: string[];
  skipped?: number;
  deleted?: string[];
  would_delete?: string[];
  error?: string | null;
}
export type LogLevel = 'info' | 'warn' | 'error';
export interface LogEvent {
  ev: 'log';
  level?: LogLevel;
  text?: string;
}
export interface RunOutputEvent {
  ev: 'run_output';
  run_id: string;
  lines?: string[];
}
export interface RunExitEvent {
  ev: 'run_exit';
  run_id: string;
  code?: number | null;
}
export interface MsgEvent {
  ev: 'msg';
  watch_id: number | string;
  topic?: string;
  t?: number;
  rate_hz?: number | null;
  data?: unknown;
}
export interface ActionEvent {
  ev: 'action';
  name: string;
  state: string;
  detail?: unknown;
}

/* 2.0 events (backend contract in the plan) */
export interface ScanEvent {
  ev: 'scan';
  t: number;
  frame: string;
  angle_min: number;
  angle_inc: number;
  range_max: number;
  ranges: Array<number | null>;
}
export interface PoseEvent {
  ev: 'pose';
  t: number;
  x: number;
  y: number;
  yaw: number;
  vx: number;
  wz: number;
  /** Present while the map stream is on: the pose in the map frame. */
  map?: MapPose;
}
export interface MapPose {
  x: number;
  y: number;
  yaw: number;
  /** "slam" is the SLAM pose moved on by odometry; "odom" means no map pose is known yet. */
  source: 'slam' | 'odom';
}

/* ---------- mapping (2.1) ---------- */

export type MappingState = 'idle' | 'starting' | 'mapping' | 'saving' | 'stopping' | 'error';

export interface MappingInfo {
  /** "unknown" is what Studio answers before it has seen the robot's state. */
  state: MappingState | 'unknown';
  since?: number;
  last_error?: string | null;
  last_saved?: { name: string; t: number } | null;
  unsaved?: boolean;
  scripts_ok?: boolean;
  other_stack?: string | null;
  maps_dir?: string;
}
export interface MappingResult {
  op: 'start' | 'save' | 'stop';
  ok: boolean;
  name?: string;
  error?: string;
  output_tail?: string[] | string;
}
export type MappingEvent = { ev: 'mapping'; result?: MappingResult } & MappingInfo;

/** The slim map event the page receives: no cells, the picture is fetched from /api/map/live.png. */
export interface MapMeta {
  seq: number;
  t: number;
  width: number;
  height: number;
  resolution: number;
  origin: { x: number; y: number; yaw: number };
  stride?: number;
}
export type MapEvent = { ev: 'map' } & MapMeta;

export interface MapEntry {
  name: string;
  width: number;
  height: number;
  resolution: number;
  origin: [number, number, number];
  mtime: number;
  bytes: number;
  files: {
    pgm: number | null;
    yaml: number | null;
    posegraph: number | null;
    data: number | null;
  };
}
export interface TeleopEvent {
  ev: 'teleop';
  armed: boolean;
  reason?: string;
}
export type AlertSeverity = 'info' | 'warn' | 'critical';
export interface Alert {
  id: number;
  t: number;
  severity: AlertSeverity;
  code: string;
  text: string;
}
export type AlertEvent = { ev: 'alert' } & Alert;

export type StudioEvent =
  | ConnEvent
  | HelloEvent
  | StatusEvent
  | DiscoverEvent
  | DeepProgressEvent
  | UpdateEvent
  | QuitEvent
  | SyncEvent
  | LogEvent
  | RunOutputEvent
  | RunExitEvent
  | MsgEvent
  | ActionEvent
  | ScanEvent
  | PoseEvent
  | MappingEvent
  | MapEvent
  | TeleopEvent
  | AlertEvent;

export type EventName = StudioEvent['ev'];
export type EventOf<K extends EventName> = Extract<StudioEvent, { ev: K }>;

/* ---------- settings ---------- */

export interface Settings {
  last_host?: string;
  key_path?: string;
  local_dir?: string;
  remote_dir?: string;
  motion_files?: string[];
  robot_hostname?: string;
  robot_user?: string;
  hotspot_ssid?: string;
  hotspot_addr?: string;
  cable_addr?: string;
  window_mode?: 'app' | 'browser';
  auto_reconnect?: boolean;
  update_check?: boolean;
  update_dismissed?: string | null;
  setup_done?: boolean;
  ui?: 'classic' | 'v2' | string;
  [key: string]: unknown;
}

export interface TrustedKey {
  key?: string;
  label?: string;
  builtin?: boolean;
  fingerprint?: string;
  added?: number;
}

export interface SettingsAnswer {
  settings: Settings;
  defaults?: Record<string, string>;
  lab_host_key?: string | null;
  trusted?: TrustedKey[];
}

/* ---------- catalog and programs ---------- */

export interface CatalogArg {
  name: string;
  help: string;
}
export interface CatalogExample {
  args: string;
  what: string;
}
export interface CatalogEntry {
  title?: string;
  summary?: string;
  moves?: boolean;
  needs_undock?: boolean;
  safe_on_dock?: boolean;
  category?: string;
  args?: CatalogArg[];
  examples?: CatalogExample[];
  stop?: string;
  notes?: string[];
  doc?: string;
}
export type CatalogTemplate = string | { name?: string; file?: string; entry?: CatalogEntry };
export interface Catalog {
  version?: number;
  programs: Record<string, CatalogEntry>;
  templates: CatalogTemplate[];
}

export interface RemoteFile {
  name: string;
  size?: number | null;
  mtime?: number | null;
  is_dir?: boolean;
  sha1?: string | null;
}

export interface ProgramDescription {
  name: string;
  size?: number;
  mtime?: number;
  docstring?: string;
  usage?: string[];
  moves_detected?: boolean;
  moves_reasons?: string[];
}

/* ---------- bridge command answers ---------- */

export interface LsAnswer {
  dir?: string;
  files: RemoteFile[];
}
export interface DescribeAnswer {
  programs: ProgramDescription[];
}
export interface ReadFileAnswer {
  path: string;
  text: string;
  size?: number;
  mtime?: number;
  sha1?: string | null;
}
export interface WriteFileAnswer {
  path: string;
  size?: number;
  sha1?: string | null;
  backup?: string | null;
  unchanged?: boolean;
}
export interface RunAnswer {
  run_id: string;
  pid?: number;
  log?: string;
}
export interface StopAnswer {
  stopped?: string[];
}
export interface HealthCheck {
  name: string;
  ok: boolean | null;
  detail?: string;
}
export interface HealthAnswer {
  checks: HealthCheck[];
}
/** Estop answer: free-form steps, shown as a tree. */
export type EstopAnswer = Record<string, unknown> & { steps?: Record<string, unknown> };

/* ---------- Studio endpoints ---------- */

export interface DiscoverAnswer {
  candidates: Candidate[];
}
export interface SyncAnswer {
  dry_run?: boolean;
  /** Files only here, and files that differ (names). */
  new?: string[];
  changed?: string[];
  uploaded?: string[];
  /** A dry run lists what a real run would transfer. */
  would_transfer?: string[];
  would_upload?: string[];
  skipped?: number;
  deleted?: string[];
  would_delete?: string[];
  direction?: 'up' | 'down';
}
export interface SyncRequest {
  local_dir: string;
  remote_dir: string;
  direction: 'up' | 'down';
  delete: boolean;
  dry_run: boolean;
  confirm_delete?: boolean;
}
export interface LocalFilesAnswer {
  files: RemoteFile[];
}
export interface OpenVscodeAnswer {
  preview?: string;
}
export interface UpdateStatusAnswer extends UpdateInfo {
  result?: 'latest' | 'newer' | 'failed';
}

/* ---------- 2.0 endpoints ---------- */

export interface HistoryAnswer {
  t: number[];
  series: Record<
    | 'battery_pct'
    | 'voltage'
    | 'current_a'
    | 'speed'
    | 'odom_hz'
    | 'scan_hz'
    | 'cpu_pct'
    | 'temp_c'
    | 'wifi_dbm',
    Array<number | null>
  >;
}
export interface AlertsAnswer {
  alerts: Alert[];
}
export interface TeleopLimits {
  linear: number;
  angular: number;
}

/* ---------- bridge commands (name -> args) ---------- */

export interface BridgeArgs {
  ls: { dir: string; recursive?: boolean };
  describe: { dir: string };
  read_file: { path: string; dir: string };
  write_file: {
    path: string;
    dir: string;
    text: string;
    overwrite?: boolean;
    expect_sha1?: string;
  };
  run: {
    path: string;
    dir: string;
    args: string[];
    motion: boolean;
    confirmed: boolean;
  };
  stop: { run_id: string };
  estop_release: Record<string, never>;
  undock: { confirmed: boolean };
  dock: { confirmed: boolean };
  lidar: { on: boolean };
  health: Record<string, never>;
  status_on: { period: number };
  topics: Record<string, never>;
  watch: { topic: string; max_hz?: number };
  unwatch: { watch_id: number };
  wifi_info: Record<string, never>;
  scan_on: { hz?: number; max_points?: number };
  scan_off: Record<string, never>;
  pose_on: { hz?: number };
  pose_off: Record<string, never>;
  teleop_arm: { on: boolean };
  teleop: { vx: number; wz: number; seq: number };
  journal: { unit: string; lines?: number; grep?: string; since?: string };
  mapping_status: Record<string, never>;
  mapping_start: { keep_camera?: boolean };
  mapping_save: { name: string; overwrite?: boolean };
  mapping_stop: Record<string, never>;
  mapping_reset: Record<string, never>;
  map_on: { hz?: number; max_cells?: number };
  map_off: Record<string, never>;
  maps_list: Record<string, never>;
  map_preview: { name: string; max_px?: number };
  map_rename: { name: string; new_name: string };
  map_delete: { name: string; confirm: true };
}
export type BridgeCmd = keyof BridgeArgs;

export interface BridgeAnswers {
  ls: LsAnswer;
  describe: DescribeAnswer;
  read_file: ReadFileAnswer;
  write_file: WriteFileAnswer;
  run: RunAnswer;
  stop: StopAnswer;
  estop_release: Record<string, never>;
  undock: Record<string, never>;
  dock: Record<string, never>;
  lidar: Record<string, never>;
  health: HealthAnswer;
  status_on: Record<string, never>;
  topics: { topics: Array<{ name: string; types?: string[]; publishers?: number }> };
  watch: { watch_id?: number };
  unwatch: Record<string, never>;
  wifi_info: Record<string, unknown>;
  scan_on: Record<string, never>;
  scan_off: Record<string, never>;
  pose_on: Record<string, never>;
  pose_off: Record<string, never>;
  teleop_arm: Record<string, never>;
  teleop: Record<string, never>;
  journal: { lines?: string[] };
  mapping_status: MappingInfo;
  mapping_start: MappingInfo;
  mapping_save: MappingInfo;
  mapping_stop: MappingInfo;
  mapping_reset: MappingInfo;
  map_on: Record<string, never>;
  map_off: Record<string, never>;
  maps_list: { maps: MapEntry[]; dir?: string };
  map_preview: {
    width: number;
    height: number;
    stride?: number;
    encoding: 'gray';
    data: string;
  };
  map_rename: { name: string };
  map_delete: { deleted: string[] };
}
