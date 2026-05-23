"""CLI: totalrecall generate — trigger a generation request."""

import json
import sys

import click

from totalrecall.cli.client import ApiError, TotalRecallClient


@click.command("generate")
@click.option("--tenant-id", required=True, help="Tenant ID")
@click.option("--application-id", required=True, help="Application ID")
@click.option("--prompt", required=True, help="Generation prompt")
@click.option("--language", default="typescript", show_default=True, help="Target language")
@click.option("--framework", default="playwright", show_default=True, help="Target framework")
@click.option("--provider", default="stub", show_default=True, help="LLM provider ID")
@click.option("--model", default="stub", show_default=True, help="Model name")
@click.option("--no-validate", is_flag=True, default=False, help="Skip artifact validation")
@click.option("--output", type=click.Choice(["json", "text"]), default="text", show_default=True)
@click.pass_context
def generate_cmd(
    ctx: click.Context,
    tenant_id: str,
    application_id: str,
    prompt: str,
    language: str,
    framework: str,
    provider: str,
    model: str,
    no_validate: bool,
    output: str,
) -> None:
    """Generate test artifacts for the given prompt."""
    client: TotalRecallClient = ctx.obj["client"]

    payload = {
        "tenant_id": tenant_id,
        "application_id": application_id,
        "prompt": prompt,
        "target": {
            "language": language,
            "framework": framework,
            "pattern": "pom",
            "locator_strategy": "page_file",
        },
        "provider": {"provider_id": provider, "model": model},
        "options": {"validate": not no_validate},
    }

    try:
        result = client.generate(payload)
    except ApiError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    if output == "json":
        click.echo(json.dumps(result, indent=2))
        return

    status = result.get("status", "unknown")
    click.echo(f"Status: {status}")
    artifacts = result.get("artifacts", [])
    click.echo(f"Artifacts: {len(artifacts)}")
    for art in artifacts:
        click.echo(f"  {art.get('path')} [{art.get('language')}]")
    validation = result.get("validation", {})
    if validation:
        click.echo(f"Validation: {validation.get('status', 'n/a')}")
        for diag in validation.get("diagnostics", []):
            click.echo(f"  [{diag['severity']}] {diag['message']}")

    if status in ("failed", "error"):
        sys.exit(2)
