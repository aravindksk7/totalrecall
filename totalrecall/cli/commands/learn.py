"""CLI: totalrecall learn — trigger and review learning runs."""

import json
import sys

import click

from totalrecall.cli.client import ApiError, TotalRecallClient


@click.group("learn")
def learn_cmd() -> None:
    """Learning run commands."""


@learn_cmd.command("run")
@click.option("--application-id", required=True, help="Application ID")
@click.option("--path", "scan_path", required=True, help="Local path to scan")
@click.option("--repository", default="local", show_default=True, help="Repository identifier")
@click.option("--branch", default="local", show_default=True, help="Branch name")
@click.option("--framework", default=None, help="Framework filter (playwright, pytest, …)")
@click.option("--domain", default=None, help="Domain tag")
@click.option("--output", type=click.Choice(["json", "text"]), default="text", show_default=True)
@click.pass_context
def learn_run(
    ctx: click.Context,
    application_id: str,
    scan_path: str,
    repository: str,
    branch: str,
    framework: str | None,
    domain: str | None,
    output: str,
) -> None:
    """Trigger a learning run on a local path."""
    client: TotalRecallClient = ctx.obj["client"]

    scope: dict = {
        "repository": repository,
        "branch": branch,
        "path": scan_path,
    }
    if framework:
        scope["framework"] = framework
    if domain:
        scope["domain"] = domain

    payload = {
        "application_id": application_id,
        "scope": scope,
        "trigger_type": "manual",
    }

    try:
        result = client.trigger_learning_run(payload)
    except ApiError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    if output == "json":
        click.echo(json.dumps(result, indent=2))
        return

    run = result.get("run", {})
    click.echo(f"Run ID:     {run.get('run_id')}")
    click.echo(f"Status:     {run.get('status')}")
    click.echo(f"Discovered: {result.get('discovered_count', 0)}")
    click.echo(f"Changed:    {result.get('changed_count', 0)}")
    click.echo(f"Unchanged:  {result.get('unchanged_count', 0)}")
    warnings = result.get("warnings", [])
    if warnings:
        click.echo(f"Warnings ({len(warnings)}):")
        for w in warnings:
            click.echo(f"  {w}")

    discoveries = run.get("discoveries", [])
    if discoveries:
        click.echo(f"\nDiscoveries ({len(discoveries)}):")
        for d in discoveries:
            delta = d.get("delta", {})
            state = delta.get("state", "?")
            dtype = d.get("discovery_type", "?")
            summ = d.get("summary", "")[:60]
            click.echo(f"  [{state:10s}] [{dtype:25s}]  {summ}")


@learn_cmd.command("list")
@click.option("--application-id", default=None, help="Filter by application ID")
@click.option("--output", type=click.Choice(["json", "table"]), default="table", show_default=True)
@click.pass_context
def learn_list(ctx: click.Context, application_id: str | None, output: str) -> None:
    """List recent learning runs."""
    client: TotalRecallClient = ctx.obj["client"]
    try:
        runs = client.list_learning_runs(application_id=application_id)
    except ApiError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    if output == "json":
        click.echo(json.dumps(runs, indent=2))
        return

    click.echo(f"Found {len(runs)} run(s):")
    for r in runs:
        run = r.get("run", {})
        click.echo(
            f"  {run.get('run_id', '?'):38s}  {run.get('status', '?'):12s}"
            f"  +{r.get('discovered_count', 0)} new  ~{r.get('changed_count', 0)} changed"
        )


@learn_cmd.command("show")
@click.argument("run_id")
@click.option("--output", type=click.Choice(["json", "text"]), default="text", show_default=True)
@click.pass_context
def learn_show(ctx: click.Context, run_id: str, output: str) -> None:
    """Show details of a learning run."""
    client: TotalRecallClient = ctx.obj["client"]
    try:
        result = client.get_learning_run(run_id)
    except ApiError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    if output == "json":
        click.echo(json.dumps(result, indent=2))
        return

    run = result.get("run", {})
    click.echo(f"Run ID:     {run.get('run_id')}")
    click.echo(f"Status:     {run.get('status')}")
    click.echo(f"Scope:      {run.get('scope', {}).get('path')}")
    click.echo(f"Started:    {run.get('started_at')}")
    click.echo(f"Completed:  {run.get('completed_at')}")
    click.echo(f"Discovered: {result.get('discovered_count', 0)}")
    click.echo(f"Changed:    {result.get('changed_count', 0)}")
    click.echo(f"Unchanged:  {result.get('unchanged_count', 0)}")
