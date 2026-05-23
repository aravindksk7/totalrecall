import {
  GeneratedArtifact,
  PlaywrightWorkerRequest,
  PlaywrightWorkerResponse,
  ValidationDiagnostic,
  ValidationStatus,
} from "./types";

function diagnostic(
  code: string,
  message: string,
  severity: ValidationStatus,
  path?: string,
  details: Record<string, unknown> = {},
): ValidationDiagnostic {
  return { code, message, severity, path: path ?? null, details };
}

function summarise(diagnostics: ValidationDiagnostic[]): ValidationStatus {
  if (diagnostics.some((item) => item.severity === "failed")) {
    return "failed";
  }
  if (diagnostics.some((item) => item.severity === "warning")) {
    return "warning";
  }
  return "passed";
}

function hasBalancedDelimiters(content: string): boolean {
  const stack: string[] = [];
  const pairs: Record<string, string> = { ")": "(", "]": "[", "}": "{" };
  let quote: string | null = null;
  let escaped = false;

  for (const char of content) {
    if (quote !== null) {
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === quote) {
        quote = null;
      }
      continue;
    }

    if (char === "\"" || char === "'" || char === "`") {
      quote = char;
      continue;
    }
    if (char === "(" || char === "[" || char === "{") {
      stack.push(char);
      continue;
    }
    if (char === ")" || char === "]" || char === "}") {
      if (stack.pop() !== pairs[char]) {
        return false;
      }
    }
  }

  return stack.length === 0 && quote === null;
}

function validateCommon(artifact: GeneratedArtifact): ValidationDiagnostic[] {
  const diagnostics: ValidationDiagnostic[] = [];
  if (artifact.content.trim().length === 0) {
    diagnostics.push(
      diagnostic(
        "EMPTY_ARTIFACT",
        `Artifact '${artifact.path}' must not be empty`,
        "failed",
        artifact.path,
      ),
    );
  }
  if (artifact.content.includes("```")) {
    diagnostics.push(
      diagnostic(
        "MARKDOWN_FENCE_IN_ARTIFACT",
        `Artifact '${artifact.path}' must contain raw code only`,
        "failed",
        artifact.path,
      ),
    );
  }
  if (!hasBalancedDelimiters(artifact.content)) {
    diagnostics.push(
      diagnostic(
        "TYPESCRIPT_SYNTAX_PRECHECK_FAILED",
        `Artifact '${artifact.path}' has unbalanced delimiters or quotes`,
        "failed",
        artifact.path,
      ),
    );
  }
  return diagnostics;
}

function validatePageObject(artifact: GeneratedArtifact): ValidationDiagnostic[] {
  const diagnostics: ValidationDiagnostic[] = [];
  if (!/\bclass\s+\w+/.test(artifact.content)) {
    diagnostics.push(
      diagnostic(
        "POM_CLASS_MISSING",
        `Page object '${artifact.path}' must define a class`,
        "failed",
        artifact.path,
      ),
    );
  }
  if (!/\bconstructor\s*\(/.test(artifact.content)) {
    diagnostics.push(
      diagnostic(
        "CONSTRUCTOR_MISSING",
        `Playwright page object '${artifact.path}' should define a constructor`,
        "warning",
        artifact.path,
      ),
    );
  }
  if (!/(getByRole|getByLabel|getByTestId|getByText|locator)\s*\(/.test(artifact.content)) {
    diagnostics.push(
      diagnostic(
        "LOCATOR_MISSING",
        `Playwright page object '${artifact.path}' should define at least one locator`,
        "warning",
        artifact.path,
      ),
    );
  }
  return diagnostics;
}

function validateSpec(artifact: GeneratedArtifact): ValidationDiagnostic[] {
  const diagnostics: ValidationDiagnostic[] = [];
  if (!/from\s+['"]@playwright\/test['"]/.test(artifact.content)) {
    diagnostics.push(
      diagnostic(
        "PLAYWRIGHT_IMPORT_MISSING",
        `Playwright spec '${artifact.path}' must import from @playwright/test`,
        "failed",
        artifact.path,
      ),
    );
  }
  if (!/\btest\s*\(/.test(artifact.content)) {
    diagnostics.push(
      diagnostic(
        "PLAYWRIGHT_TEST_MISSING",
        `Playwright spec '${artifact.path}' must define at least one test() call`,
        "failed",
        artifact.path,
      ),
    );
  }
  return diagnostics;
}

export function validatePlaywrightArtifacts(
  request: PlaywrightWorkerRequest,
): PlaywrightWorkerResponse {
  const diagnostics: ValidationDiagnostic[] = [];
  const artifacts = request.artifacts.filter((artifact) => artifact.language === "typescript");

  for (const artifact of artifacts) {
    diagnostics.push(...validateCommon(artifact));
    if (artifact.artifact_type === "page_object") {
      diagnostics.push(...validatePageObject(artifact));
    }
    if (artifact.artifact_type === "test_spec") {
      diagnostics.push(...validateSpec(artifact));
    }
  }

  return { status: summarise(diagnostics), diagnostics };
}
