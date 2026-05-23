export type ValidationStatus = "not_run" | "passed" | "failed" | "warning";
export type Language = "python" | "typescript" | "java";
export type ArtifactType = "page_object" | "test_spec" | "fixture" | "config" | "support";

export interface GeneratedArtifact {
  path: string;
  language: Language;
  content: string;
  artifact_type: ArtifactType;
}

export interface ValidationDiagnostic {
  code: string;
  message: string;
  path?: string | null;
  severity: ValidationStatus;
  details?: Record<string, unknown>;
}

export interface PlaywrightWorkerRequest {
  request_id: string;
  artifacts: GeneratedArtifact[];
}

export interface PlaywrightWorkerResponse {
  status: ValidationStatus;
  diagnostics: ValidationDiagnostic[];
}
