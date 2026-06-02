/**
 * 后端契约 TS 类型(按货架 FastAPI schema 手写,见 backend/app/schemas/)。
 */

export interface ScriptListItem {
  slug: string;
  name: string;
  description: string | null;
  version: string;
  author: string | null;
  homepage: string | null;
  tags: string[];
  field_count: number;
  file_count: number;
  size_bytes: number;
  download_count: number;
  has_icon: boolean;
  updated_at: string;
}

export interface FieldSummary {
  key: string;
  label: string;
  type: string;
  required: boolean;
}

export interface ScriptDetail extends ScriptListItem {
  manifest_yaml: string;
  fields_summary: FieldSummary[];
  bundle_sha256: string;
  icon_svg: string | null;
  created_at: string;
}

export interface FileItem {
  path: string;
  size: number;
  editable: boolean;
}

export interface FileListResponse {
  slug: string;
  files: FileItem[];
}

export interface FileContentResponse {
  slug: string;
  path: string;
  content: string;
}

export interface UploadResponse {
  slug: string;
  name: string;
  version: string;
  created: boolean;
}

// ===== 鉴权 =====
export interface UserResponse {
  id: number;
  username: string;
  display_name: string | null;
  is_admin: boolean;
}

export interface SetupStateResponse {
  setup_required: boolean;
}

export interface HealthResponse {
  status: string;
  app: string;
}

// ===== 统一错误体 =====
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}
