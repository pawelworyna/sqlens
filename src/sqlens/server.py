"""FastMCP Server for SQLens - compatible with GitHub Copilot (VS Code & CLI), Antigravity, OpenAI Codex, and Hermes."""

from __future__ import annotations

import logging
import sys
import warnings
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sqlens.db import extract_schema, run_readonly_query

# Configure all logging and warnings strictly to stderr so stdout remains clean for MCP JSON-RPC over stdio
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
warnings.filterwarnings("ignore")

SERVER_INSTRUCTIONS = (
    "SQLens is a read-only database inspection MCP server supporting SQLite, SQL Server (MSSQL), "
    "PostgreSQL, and MySQL.\n"
    "MANDATORY WORKFLOW:\n"
    "1. ALWAYS call `inspect_database(connection_target=...)` FIRST to verify that the database exists / "
    "is reachable, discover its SQL dialect (`sqlite`, `mssql`, `postgresql`, `mysql`), and retrieve "
    "its full schema (tables, views, columns, data types, primary keys, and foreign keys).\n"
    "2. If `exists` is False, stop and report the error to the user immediately.\n"
    "3. Only AFTER inspecting the schema, translate the user's intent into a valid read-only SQL query "
    "matching the discovered schema and dialect (e.g. `SELECT TOP N` for `mssql` vs `LIMIT N` for "
    "`sqlite`/`postgresql`/`mysql`) and call `execute_query(connection_target=..., sql_query=...)`."
)

mcp = FastMCP(
    "sqlens",
    instructions=SERVER_INSTRUCTIONS,
)

READONLY_TOOL_ANNOTATIONS = ToolAnnotations(
    title="SQLens Read-Only Database Tool",
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


@mcp.tool(annotations=READONLY_TOOL_ANNOTATIONS)
def inspect_database(connection_target: str, schema_name: str = "") -> dict[str, Any]:
    """
    STEP 1 (MANDATORY BEFORE RUNNING ANY QUERY): Verifies if the target database (SQLite file,
    SQL Server, PostgreSQL, or MySQL) exists and is reachable, and returns its SQL dialect
    along with the complete schema (tables, views, columns, types, primary keys, and foreign keys).

    ALWAYS call this tool FIRST for any `connection_target` before calling `execute_query`.
    Never guess table or column names without calling `inspect_database` first.

    Args:
        connection_target: Path to a SQLite database file (e.g. 'C:/data/app.db'), a database URI
            (e.g. 'mssql+pymssql://user:pass@host:1433/db', 'postgresql://...', 'mysql://...'),
            a raw SQL Server ODBC connection string, or a profile variable name from `.env`.
        schema_name: Optional database schema filter (e.g. 'dbo' for SQL Server, 'public' for PostgreSQL).
            Leave empty ('') to inspect default/all user schemas.
    """
    return extract_schema(connection_target=connection_target, schema_name=schema_name or None)


@mcp.tool(annotations=READONLY_TOOL_ANNOTATIONS)
def execute_query(connection_target: str, sql_query: str, max_rows: int = 100) -> dict[str, Any]:
    """
    STEP 2: Executes a read-only SQL query (SELECT, WITH, EXPLAIN, PRAGMA, SHOW, DESCRIBE)
    against a database (SQLite, SQL Server, PostgreSQL, or MySQL) and returns the rows.

    PREREQUISITE: You MUST call `inspect_database` for this `connection_target` BEFORE calling
    `execute_query` so you know the database exists, its exact SQL dialect (e.g. T-SQL `TOP N` for
    SQL Server vs `LIMIT N` for SQLite/PostgreSQL/MySQL), and the exact table and column names.

    Args:
        connection_target: The database path, URI, ODBC connection string, or `.env` profile name
            that was previously verified with `inspect_database`.
        sql_query: A single read-only SQL query constructed based on the user's intent and the schema
            returned by `inspect_database`. Modifying statements (INSERT, UPDATE, DELETE, DROP, etc.) are blocked.
        max_rows: Maximum number of rows to return (default 100, maximum 1000).
    """
    return run_readonly_query(
        connection_target=connection_target,
        sql_query=sql_query,
        max_rows=max_rows,
    )


@mcp.prompt()
def inspect_and_query(connection_target: str, intent: str) -> str:
    """
    Guided workflow prompt for inspecting a database and answering a user's question with SQL.
    """
    return (
        f"Chcę zbadać bazę danych: `{connection_target}`.\n"
        f"Mój cel / pytanie: {intent}\n\n"
        "Postępuj ściśle według poniższych kroków:\n"
        "1. Najpierw wywołaj narzędzie `inspect_database(connection_target=...)`, aby sprawdzić czy baza istnieje "
        "i pobrać jej dialekt oraz pełny schemat (tabele, widoki, kolumny, klucze główne i obce).\n"
        "2. Jeśli baza nie istnieje lub połączenie się nie powiedzie, poinformuj mnie o błędzie i zakończ.\n"
        "3. Na podstawie pobranego schematu oraz dialektu bazy ułóż odpowiednie zapytanie tylko do odczytu (SELECT) "
        "realizujące mój cel i wywołaj `execute_query(connection_target=..., sql_query=...)`.\n"
        "4. Przedstaw czytelne podsumowanie wyników wraz z użytym zapytaniem SQL."
    )


def main() -> None:
    """Runs the SQLens MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
