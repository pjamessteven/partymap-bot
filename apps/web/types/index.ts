// Types generated from OpenAPI spec

export type FestivalState = 
  | 'discovered' 
  | 'researching' 
  | 'researched' 
  | 'syncing' 
  | 'synced' 
  | 'failed' 
  | 'skipped' 
  | 'needs_review';

export type FestivalAction = 
  | 'deduplicate' 
  | 'research' 
  | 'sync' 
  | 'skip' 
  | 'retry' 
  | 'reset';

export type FestivalActionResult = 
  | 'queued' 
  | 'completed' 
  | 'skipped' 
  | 'failed';

export type SettingCategory = 
  | 'pipeline' 
  | 'scheduling' 
  | 'cost' 
  | 'general';

export type SettingValueType = 
  | 'string' 
  | 'boolean' 
  | 'integer' 
  | 'float' 
  | 'json';

export interface Festival {
  id: string;
  name: string;
  source: string;
  source_url?: string;
  state: FestivalState;
  is_duplicate?: boolean;
  is_new_event_date?: boolean;
  date_confirmed?: boolean;
  partymap_event_id?: string | null;
  partymap_date_id?: string | null;
  retry_count: number;
  last_error?: string | null;
  discovery_cost_cents?: number;
  research_cost_cents?: number;
  total_cost_cents?: number;
  event_dates?: Array<Record<string, unknown>>;
  decisions?: Array<Record<string, unknown>>;
  discovered_data?: Record<string, unknown>;
  research_data?: Record<string, unknown>;
  current_thread_id?: string;
  created_at: string;
  updated_at: string;
}

export interface FestivalEventDate {
  id: string;
  festival_id: string;
  start_date?: string;
  end_date?: string;
  location?: string;
  venue?: string;
  lineup?: string[];
  ticket_url?: string;
  price_info?: string;
  size_estimate?: string;
  created_at: string;
  updated_at: string;
}

export interface FestivalPendingAction {
  festival_id: string;
  name: string;
  state: FestivalState;
  source: string;
  suggested_action: FestivalAction;
  action_description: string;
  created_at: string;
  retry_count: number;
  last_error?: string;
}

export interface FestivalActionResponse {
  festival_id: string;
  action: FestivalAction;
  result: FestivalActionResult;
  message: string;
  previous_state: FestivalState;
  new_state?: FestivalState;
  task_id?: string;
  queued: boolean;
  timestamp: string;
}

export interface DeduplicationResultResponse {
  festival_id: string;
  is_duplicate: boolean;
  existing_event_id?: string;
  is_new_event_date: boolean;
  date_confirmed: boolean;
  confidence: number;
  reason: string;
  action_taken: string;
  auto_queued: boolean;
}

export interface ScheduleConfig {
  id: string;
  task_type: string;
  enabled: boolean;
  hour: number;
  minute: number;
  day_of_week?: number;
  last_run_at?: string;
  next_run_at?: string;
  run_count: number;
  created_at: string;
  updated_at: string;
}

export interface ScheduleUpdate {
  enabled?: boolean;
  hour?: number;
  minute?: number;
  day_of_week?: number;
}

export interface ScheduleApplyResponse {
  message: string;
  refreshed_at: string;
  active_schedules: number;
}

export interface ScheduleRunResponse {
  message: string;
  task_type: string;
  task_id?: string;
}

export interface SystemSetting {
  id: string;
  key: string;
  value: unknown;
  value_type: SettingValueType;
  description?: string;
  editable: boolean;
  category: SettingCategory;
  created_at: string;
  updated_at: string;
}

export interface SystemSettingResponse {
  id: string;
  key: string;
  value: unknown;
  value_type: SettingValueType;
  description?: string;
  editable: boolean;
  category: SettingCategory;
  created_at: string;
  updated_at: string;
}

export interface SettingsListResponse {
  settings: SystemSettingResponse[];
  by_category: Record<SettingCategory, SystemSettingResponse[]>;
}

export interface AutoProcessSetting {
  enabled: boolean;
  description: string;
}

export interface DiscoveryQuery {
  id: string;
  query_text: string;
  category: string;
  enabled: boolean;
  last_run_at?: string;
  run_count: number;
  created_at: string;
  updated_at: string;
}

export interface CostLog {
  id: string;
  festival_id?: string;
  agent_type: string;
  operation: string;
  cost_cents: number;
  details?: Record<string, unknown>;
  created_at: string;
}

export interface Stats {
  total_festivals: number;
  by_state: Record<FestivalState, number>;
  today_cost_cents: number;
  week_cost_cents: number;
  month_cost_cents: number;
  pending_count: number;
  failed_count: number;
}

export interface JobStatus {
  [key: string]: JobStatusDetail | undefined;
  discovery?: JobStatusDetail;
  goabase_sync?: JobStatusDetail;
  goabase?: JobStatusDetail;
  research?: JobStatusDetail;
  sync?: JobStatusDetail;
}

export interface JobStatusDetail {
  status: string;
  task_id?: string;
  started_at?: string;
  metadata?: Record<string, unknown>;
  stopped_at?: string;
  currently_processing?: Array<{
    id: string;
    name: string;
    started_at: string;
  }>;
  // Computed fields
  running?: boolean;
  completed_at?: string;
  failed_at?: string;
  error?: string;
  progress?: {
    current: number;
    total: number;
    percent: number;
  };
  result?: Record<string, unknown>;
}

export interface FestivalListResponse {
  festivals: Festival[];
  total: number;
  offset: number;
  limit: number;
}

export interface GoabaseSyncStatus {
  is_running: boolean;
  started_at?: string;
  completed_at?: string;
  total_found: number;
  new_count: number;
  update_count: number;
  unchanged_count: number;
  error_count: number;
  current_operation?: string;
  stop_requested: boolean;
  progress_percentage: number;
}

export interface GoabaseSettings {
  goabase_sync_enabled: boolean;
  goabase_sync_frequency: 'daily' | 'weekly' | 'monthly';
  goabase_sync_day: 'monday' | 'tuesday' | 'wednesday' | 'thursday' | 'friday' | 'saturday' | 'sunday';
  goabase_sync_hour: number;
}
