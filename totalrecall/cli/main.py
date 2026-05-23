"""TotalRecall CLI entry point."""

import os

import click

from totalrecall.cli.client import TotalRecallClient
from totalrecall.cli.commands.catalogue import catalogue_cmd
from totalrecall.cli.commands.generate import generate_cmd
from totalrecall.cli.commands.learn import learn_cmd


@click.group()
@click.option(
    "--url",
    envvar="TOTALRECALL_URL",
    default="http://localhost:8000",
    show_default=True,
    help="TotalRecall service base URL",
)
@click.option(
    "--token",
    envvar="TOTALRECALL_TOKEN",
    default=None,
    help="Bearer token for authentication",
)
@click.pass_context
def cli(ctx: click.Context, url: str, token: str | None) -> None:
    """TotalRecall — context-driven test automation orchestration CLI."""
    ctx.ensure_object(dict)
    resolved_token = token or os.environ.get("TOTALRECALL_TOKEN", "")
    ctx.obj["client"] = TotalRecallClient(base_url=url, token=resolved_token)


cli.add_command(generate_cmd)
cli.add_command(catalogue_cmd)
cli.add_command(learn_cmd)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
