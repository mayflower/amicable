export type DesignApproach = {
  approach_id: string;
  title: string;
  rationale: string;
  render_prompt: string;
  image_base64: string;
  mime_type: string;
  width: number;
  height: number;
};

export type DesignState = {
  project_id: string;
  path: string;
  viewport_width: number;
  viewport_height: number;
  approaches: DesignApproach[];
  selected_approach_id: string | null;
  total_iterations: number;
  pending_continue_decision: boolean;
  last_user_instruction: string | null;
  updated_at_ms: number;
};

export type DesignSnapshotResponse = {
  ok: boolean;
  image_base64: string | null;
  mime_type: string;
  width: number;
  height: number;
  path: string;
  target_url: string | null;
  error: string | null;
};

export type DesignGeneratePayload = {
  path?: string;
  viewport_width?: number;
  viewport_height?: number;
  full_page?: boolean;
  instruction?: string;
  device_type?: "mobile" | "tablet" | "desktop";
};
