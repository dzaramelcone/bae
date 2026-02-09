"""Bae CLI - Type-driven agent graphs with DSPy optimization.

Commands:
    bae graph show <module>    Open graph visualization in mermaid.live
    bae graph export <module>  Export graph to file (requires mmdc)
"""

from __future__ import annotations

import asyncio
import base64
import importlib
import json
import subprocess
import webbrowser
import zlib
from pathlib import Path
from typing import Annotated, Optional

import typer

from bae import Graph


def _encode_mermaid_for_live(code: str) -> str:
    """Encode mermaid diagram for mermaid.live URL.

    Uses pako compression format that mermaid.live expects.
    """
    state = {"code": code, "mermaid": {"theme": "default"}}
    json_str = json.dumps(state)

    # Compress with zlib (pako-compatible settings)
    compress = zlib.compressobj(9, zlib.DEFLATED, 15, 8, zlib.Z_DEFAULT_STRATEGY)
    compressed = compress.compress(json_str.encode("utf-8")) + compress.flush()

    # Base64 encode with URL-safe substitutions
    encoded = base64.b64encode(compressed).decode("ascii")
    encoded = encoded.replace("+", "-").replace("/", "_")

    return f"pako:{encoded}"

app = typer.Typer(
    name="bae",
    help="Type-driven agent graphs with DSPy optimization",
    no_args_is_help=True,
)
graph_app = typer.Typer(help="Graph visualization commands")
app.add_typer(graph_app, name="graph")


def _load_graph_from_module(module_path: str) -> Graph:
    """Load a Graph from a module path.

    Supports:
    - Module with create_graph() function: myapp.graphs.weather
    - Module with Graph instance named 'graph': myapp.graphs.weather:graph
    - Direct class reference: myapp.graphs.weather:StartNode (creates Graph from node)
    """
    if ":" in module_path:
        module_name, attr_name = module_path.rsplit(":", 1)
    else:
        module_name = module_path
        attr_name = None

    try:
        module = importlib.import_module(module_name)
    except ImportError as e:
        raise typer.BadParameter(f"Cannot import module '{module_name}': {e}")

    # If attribute specified, get it directly
    if attr_name:
        if not hasattr(module, attr_name):
            raise typer.BadParameter(f"Module '{module_name}' has no attribute '{attr_name}'")
        obj = getattr(module, attr_name)
        if isinstance(obj, Graph):
            return obj
        elif isinstance(obj, type):
            # Assume it's a Node class, create graph from it
            return Graph(start=obj)
        else:
            raise typer.BadParameter(
                f"'{attr_name}' is not a Graph or Node class, got {type(obj).__name__}"
            )

    # Look for create_graph() function
    if hasattr(module, "create_graph"):
        return module.create_graph()

    # Look for 'graph' attribute
    if hasattr(module, "graph"):
        obj = module.graph
        if isinstance(obj, Graph):
            return obj

    raise typer.BadParameter(
        f"Module '{module_name}' has no create_graph() function or 'graph' attribute. "
        "Use module:GraphClass or module:NodeClass syntax."
    )


@graph_app.command("show")
def graph_show(
    module: Annotated[
        str,
        typer.Argument(
            help="Module path to load graph from (e.g., 'myapp.graphs:StartNode')"
        ),
    ],
    no_browser: Annotated[
        bool,
        typer.Option("--no-browser", "-n", help="Print URL instead of opening browser"),
    ] = False,
):
    """Open graph visualization in mermaid.live.

    Examples:
        bae graph show examples.weather_outfit
        bae graph show myapp.agents:TaskRouter
    """
    graph = _load_graph_from_module(module)
    mermaid = graph.to_mermaid()

    typer.echo("Mermaid diagram:")
    typer.echo(mermaid)
    typer.echo()

    # Encode for mermaid.live (pako compression)
    encoded = _encode_mermaid_for_live(mermaid)
    url = f"https://mermaid.live/edit#{encoded}"

    if no_browser:
        typer.echo(f"URL: {url}")
    else:
        typer.echo(f"Opening: {url[:60]}...")
        webbrowser.open(url)


@graph_app.command("export")
def graph_export(
    module: Annotated[
        str,
        typer.Argument(help="Module path to load graph from"),
    ],
    output: Annotated[
        Path,
        typer.Option("-o", "--output", help="Output file path"),
    ] = Path("graph.svg"),
    format: Annotated[
        str,
        typer.Option("-f", "--format", help="Output format (svg, png, pdf)"),
    ] = "svg",
):
    """Export graph to image file (requires mermaid-cli: npm install -g @mermaid-js/mermaid-cli).

    Examples:
        bae graph export examples.weather_outfit -o weather.svg
        bae graph export myapp.agents:TaskRouter -f png
    """
    graph = _load_graph_from_module(module)
    mermaid = graph.to_mermaid()

    # Check if mmdc is available
    try:
        subprocess.run(["mmdc", "--version"], capture_output=True, check=True)
    except FileNotFoundError:
        typer.echo(
            "Error: mermaid-cli (mmdc) not found. Install with:",
            err=True,
        )
        typer.echo("  npm install -g @mermaid-js/mermaid-cli", err=True)
        raise typer.Exit(1)

    # Write mermaid to temp file
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".mmd", delete=False) as f:
        f.write(mermaid)
        mmd_path = f.name

    # Ensure output has correct extension
    if not output.suffix:
        output = output.with_suffix(f".{format}")

    try:
        result = subprocess.run(
            ["mmdc", "-i", mmd_path, "-o", str(output), "-f", format],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            typer.echo(f"Error: {result.stderr}", err=True)
            raise typer.Exit(1)

        typer.echo(f"Exported to: {output}")

    finally:
        Path(mmd_path).unlink(missing_ok=True)


@graph_app.command("mermaid")
def graph_mermaid(
    module: Annotated[
        str,
        typer.Argument(help="Module path to load graph from"),
    ],
):
    """Print mermaid diagram to stdout.

    Examples:
        bae graph mermaid examples.weather_outfit
        bae graph mermaid myapp.agents:StartNode > graph.mmd
    """
    graph = _load_graph_from_module(module)
    typer.echo(graph.to_mermaid())


@app.command("run")
def run_graph(
    module: Annotated[
        str,
        typer.Argument(help="Module path to load graph from"),
    ],
    input_json: Annotated[
        Optional[str],
        typer.Option("--input", "-i", help="JSON input for start node"),
    ] = None,
    backend: Annotated[
        str,
        typer.Option("-b", "--backend", help="LLM backend (dspy, claude)"),
    ] = "dspy",
):
    """Run a graph with optional input.

    Examples:
        bae run examples.weather_outfit -i '{"location": "Seattle"}'
    """
    import json

    graph = _load_graph_from_module(module)

    # Get the start node class
    start_cls = graph.start

    # Parse input
    if input_json:
        try:
            data = json.loads(input_json)
        except json.JSONDecodeError as e:
            raise typer.BadParameter(f"Invalid JSON: {e}")
        start_node = start_cls(**data)
    else:
        # Try to create with defaults
        try:
            start_node = start_cls()
        except TypeError:
            typer.echo(f"Error: {start_cls.__name__} requires input. Use --input with JSON.")
            raise typer.Exit(1)

    # Get LM backend
    if backend == "claude":
        from bae import ClaudeCLIBackend

        lm = ClaudeCLIBackend(model="claude-sonnet-4-20250514")
    else:
        lm = None  # Uses DSPyBackend by default

    typer.echo(f"Running {graph.start.__name__}...")
    result = asyncio.run(graph.run(start_node, lm=lm))

    typer.echo("\nTrace:")
    for i, node in enumerate(result.trace):
        typer.echo(f"  {i + 1}. {type(node).__name__}")

    typer.echo(f"\nFinal: {result.node}")


def main():
    app()


if __name__ == "__main__":
    main()
