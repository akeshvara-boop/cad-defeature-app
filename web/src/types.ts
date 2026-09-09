export type JsonRecord = Record<string, unknown>;

export interface WorkflowEvent {
  at: string;
  action: string;
  status: string;
  run_dir?: string | null;
}

export interface WorkflowState extends JsonRecord {
  workflow_id: string;
  created_at: string;
  updated_at: string;
  phase: string;
  status: string;
  host_source: string;
  source_model: string;
  active_model: string;
  events: WorkflowEvent[];
  health?: JsonRecord;
  healing?: JsonRecord;
  analysis?: JsonRecord;
  verification?: JsonRecord;
  tolerance_request?: JsonRecord | null;
  cfd_mesh_handoff?: {
    status: string;
    message: string;
  };
}

export interface FrontendConfig {
  product: string;
  api_version: string;
  kit_stream: {
    signaling_host: string;
    signaling_port: number;
    media_port: number | null;
  };
  capabilities: Record<string, string>;
}
