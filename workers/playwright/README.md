# TotalRecall Playwright Worker

This package is the TypeScript companion worker for Playwright-native validation.
The Python service calls it through a stdin/stdout JSON contract and never imports
Node, TypeScript, or Playwright packages directly.

## Contract

Run the worker with a validation request on stdin:

```bash
node dist/cli.js < contracts/validation-request.sample.json
```

It returns a `PlaywrightWorkerResponse` JSON document:

```json
{
  "status": "passed",
  "diagnostics": []
}
```

Validation failures are reported in the response body. Process exit codes are
reserved for malformed input or runtime failures.

## Local Development

```bash
npm install
npm run build
npm run validate < contracts/validation-request.sample.json
```

The checked-in `dist/` files keep the worker runnable in Python-only test
environments where npm dependencies are not installed.
