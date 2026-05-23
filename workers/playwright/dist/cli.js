"use strict";

const { readFileSync } = require("node:fs");
const { stdin, stdout, stderr, exit } = require("node:process");
const { validatePlaywrightArtifacts } = require("./validator");

function readStdin() {
  return readFileSync(stdin.fd, "utf8");
}

function isRequest(value) {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value;
  return (
    typeof candidate.request_id === "string" &&
    Array.isArray(candidate.artifacts) &&
    candidate.artifacts.every((artifact) => {
      if (typeof artifact !== "object" || artifact === null) {
        return false;
      }
      const item = artifact;
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
  const parsed = JSON.parse(input);
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
