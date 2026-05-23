"""CLI: totalrecall catalogue — search and manage catalogue entries."""

import json
import sys

import click

from totalrecall.cli.client import ApiError, TotalRecallClient


@click.group("catalogue")
def catalogue_cmd() -> None:
    """Catalogue management commands."""


@catalogue_cmd.command("search")
@click.option("--application-id", default=None, help="Filter by application ID")
@click.option("--category", default=None, help="Filter by category (static_skill, dynamic_memory…)")
@click.option("--status", "entry_status", default=None, help="Status filter (active, discovered…)")
@click.option("--limit", default=20, show_default=True, type=int)
@click.option("--output", type=click.Choice(["json", "table"]), default="table", show_default=True)
@click.pass_context
def catalogue_search(
    ctx: click.Context,
    application_id: str | None,
    category: str | None,
    entry_status: str | None,
    limit: int,
    output: str,
) -> None:
    """Search catalogue entries."""
    client: TotalRecallClient = ctx.obj["client"]
    params = {
        "application_id": application_id,
        "category": category,
        "status": entry_status,
        "limit": limit,
    }
    try:
        result = client.search_catalogue(params)
    except ApiError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    if output == "json":
        click.echo(json.dumps(result, indent=2))
        return

    items = result.get("items", [])
    total = result.get("total", 0)
    click.echo(f"Found {total} entries (showing {len(items)}):")
    for item in items:
        eid = item["entity_id"]
        cat = item["category"]
        st = item["status"]
        summ = item["summary"][:60]
        click.echo(f"  {eid:36s}  [{cat:20s}]  {st:12s}  {summ}")


@catalogue_cmd.command("get")
@click.argument("entity_id")
@click.option("--output", type=click.Choice(["json", "text"]), default="text", show_default=True)
@click.pass_context
def catalogue_get(ctx: click.Context, entity_id: str, output: str) -> None:
    """Get a catalogue entry by ID."""
    client: TotalRecallClient = ctx.obj["client"]
    try:
        entry = client.get_catalogue_entry(entity_id)
    except ApiError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    if output == "json":
        click.echo(json.dumps(entry, indent=2))
        return

    click.echo(f"ID:       {entry['entity_id']}")
    click.echo(f"Category: {entry['category']}")
    click.echo(f"Status:   {entry['status']}")
    click.echo(f"Summary:  {entry['summary']}")
    click.echo(f"Tags:     {entry.get('tags', {})}")


@catalogue_cmd.command("delete-memory")
@click.argument("entity_id")
@click.option("--application-id", required=True, help="Application ID")
@click.option("--reason", default=None, help="Reason for deletion")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def catalogue_delete_memory(
    ctx: click.Context,
    entity_id: str,
    application_id: str,
    reason: str | None,
    yes: bool,
) -> None:
    """Tombstone a memory entry (requires memory:delete permission)."""
    if not yes:
        click.confirm(f"Delete memory '{entity_id}'?", abort=True)

    client: TotalRecallClient = ctx.obj["client"]
    try:
        result = client.delete_memory(entity_id, application_id, reason)
    except ApiError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    deleted = result.get("deleted", False)
    tombstoned = result.get("tombstoned", False)
    click.echo(f"Deleted: {deleted}, Tombstoned: {tombstoned}")
