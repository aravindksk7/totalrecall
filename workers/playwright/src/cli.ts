import { readFileSync } from "node:fs";
import { stdin, stdout, stderr, exit } from "node:process";
import { validatePlaywrightArtifacts } from "./validator";
import { PlaywrightWorkerRequest } from "./types";

function readStdin(): string {
  return readFileSync(stdin.fd, "utf8");
}

function isRequest(value: unknown): value is PlaywrightWorkerRequest {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.request_id === "string" &&
    Array.isArray(candidate.artifacts) &&
    candidate.artifacts.every((artifact) => {
      if (typeof artifact !== "object" || artifact === null) {
        return false;
      }
      const item = artifact as Record<string, unknown>;
      return (
        typeof item.path === "string" &&
        typeof item.language === "string" &&
        typeof item.artifact_type === "string" &&
        typeof item.content === "string"
      );
    })
  );
}

try {
  const input = readStdin();
  const parsed: unknown = JSON.parse(input);
  if (!isRequest(parsed)) {
    stderr.write("Invalid PlaywrightWorkerRequest\n");
    exit(2);
  }
  stdout.write(`${JSON.stringify(validatePlaywrightArtifacts(parsed))}\n`);
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  stderr.write(`Playwright worker failed: ${message}\n`);
  exit(2);
}
