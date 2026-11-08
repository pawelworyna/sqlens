"""Database schema inspection and read-only SQL execution across SQLite, SQL Server, PostgreSQL, and MySQL."""

from __future__ import annotations

import datetime
import decimal
import re
import uuid
from typing import Any

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from sqlens.resolver import DIALECT_HINTS, ResolvedTarget, resolve_target

ALLOWED_START_KEYWORDS = {
    "SELECT",
    "WITH",
    "EXPLAIN",
    "PRAGMA",
    "SHOW",
    "DESCRIBE",
    "DESC",
}

FORBIDDEN_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "CREATE",
    "REPLACE",
    "UPSERT",
    "MERGE",
    "EXEC",
    "EXECUTE",
    "CALL",
    "GRANT",
    "REVOKE",
    "ATTACH",
    "DETACH",
    "VACUUM",
    "REINDEX",
    "BACKUP",
    "RESTORE",
    "SHUTDOWN",
    "KILL",
}

# Precompiled regexes for stripping comments and string literals during SQL validation
_SQL_COMMENT_RE = re.compile(r"(--[^\r\n]*)|(/\*[\s\S]*?\*/)")
_SQL_STRING_RE = re.compile(r"('(?:''|[^'])*')|(\"(?:\"\"|[^\"])*\")|(\[[^\]]*\])|(`[^`]*`)")


def _strip_comments_and_literals(sql: str) -> str:
    """Removes SQL comments and replaces string/identifier literals with placeholders for safe token scanning."""
    no_comments = _SQL_COMMENT_RE.sub(" ", sql)
    no_literals = _SQL_STRING_RE.sub(" '' ", no_comments)
    return no_literals.strip()


def validate_readonly_sql(sql_query: str) -> tuple[bool, str]:
    """
    Validates that the SQL query is strictly read-only and contains only a single statement.

    Returns:
        (is_valid, error_message)
    """
    if not sql_query or not sql_query.strip():
        return False, "SQL query cannot be empty."

    cleaned = _strip_comments_and_literals(sql_query)
    if not cleaned:
        return False, "SQL query contains only comments or whitespace."

    # Strip trailing semicolons and ensure no internal semicolons (prevent stacked queries)
    without_trailing_semi = cleaned.rstrip("; \t\r\n")
    if ";" in without_trailing_semi:
        return (
            False,
            "Multiple SQL statements separated by semicolons are not allowed. Execute one read-only query at a time.",
        )

    tokens = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", without_trailing_semi.upper())
    if not tokens:
        return False, "Could not parse any valid SQL keywords from the query."

    first_token = tokens[0]
    if first_token not in ALLOWED_START_KEYWORDS:
        return (
            False,
            f"Query must start with a read-only keyword ({', '.join(sorted(ALLOWED_START_KEYWORDS))}). "
            f"Found: '{first_token}'.",
        )

    # Disallow modifying PRAGMAs in SQLite (e.g., PRAGMA writable_schema = 1 or PRAGMA journal_mode = ...)
    if first_token == "PRAGMA" and "=" in without_trailing_semi:
        return False, "Modifying PRAGMA statements (containing '=') are not allowed in read-only mode."

    # Check for forbidden modifying keywords anywhere in the statement outside literals
    for token in tokens:
        if token in FORBIDDEN_KEYWORDS:
            return (
                False,
                f"Forbidden modifying keyword '{token}' detected. Only read-only queries are permitted.",
            )

    # Disallow SELECT ... INTO which creates a new table in SQL Server / PostgreSQL
    if re.search(r"\bSELECT\b[\s\S]+\bINTO\b", without_trailing_semi, flags=re.IGNORECASE):
        return False, "`SELECT ... INTO` is not allowed in read-only mode because it creates a table."

    return True, ""


def _serialize_value(val: Any) -> Any:
    """Converts database column values into JSON-serializable Python types."""
    if val is None or isinstance(val, (str, int, float, bool)):
        return val
    if isinstance(val, (datetime.datetime, datetime.date, datetime.time)):
        return val.isoformat()
    if isinstance(val, datetime.timedelta):
        return str(val)
    if isinstance(val, decimal.Decimal):
        return float(val) if val.is_finite() else str(val)
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, (bytes, bytearray, memoryview)):
        raw_bytes = bytes(val)
        try:
            return raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return f"<bytes len={len(raw_bytes)} hex={raw_bytes[:32].hex()}>"
    return str(val)


def create_readonly_engine(resolved: ResolvedTarget) -> Engine:
    """Creates a SQLAlchemy engine configured for read-only inspection and querying."""
    connect_args: dict[str, Any] = {}
    if resolved.dialect == "sqlite":
        connect_args["timeout"] = 5
    elif resolved.dialect == "mssql":
        if "pyodbc" in resolved.sqlalchemy_url:
            connect_args["timeout"] = 10
        elif "pymssql" in resolved.sqlalchemy_url:
            connect_args["login_timeout"] = 10
            connect_args["timeout"] = 30
    elif resolved.dialect in ("postgresql", "mysql"):
        connect_args["connect_timeout"] = 10

    engine = create_engine(
        resolved.sqlalchemy_url,
        connect_args=connect_args,
        pool_pre_ping=True,
    )

    if resolved.dialect == "sqlite":
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA query_only = ON")
            cursor.close()

    return engine


def _build_table_metadata(inspector: Any, table_name: str, schema: str | None, item_type: str) -> dict[str, Any]:
    """Extracts columns, primary keys, and foreign keys for a single table or view."""
    columns_info: list[dict[str, Any]] = []
    pk_columns: set[str] = set()

    try:
        pk_constraint = inspector.get_pk_constraint(table_name, schema=schema)
        if pk_constraint and pk_constraint.get("constrained_columns"):
            pk_columns = set(pk_constraint["constrained_columns"])
    except Exception:
        pass

    try:
        raw_columns = inspector.get_columns(table_name, schema=schema)
        for col in raw_columns:
            col_name = col.get("name", "")
            columns_info.append(
                {
                    "name": col_name,
                    "type": str(col.get("type", "UNKNOWN")),
                    "nullable": bool(col.get("nullable", True)),
                    "default": str(col["default"]) if col.get("default") is not None else None,
                    "primary_key": col_name in pk_columns or bool(col.get("primary_key", False)),
                }
            )
    except Exception as exc:
        columns_info.append({"error": f"Could not inspect columns: {exc}"})

    foreign_keys_info: list[dict[str, Any]] = []
    if item_type == "table":
        try:
            raw_fks = inspector.get_foreign_keys(table_name, schema=schema)
            for fk in raw_fks:
                foreign_keys_info.append(
                    {
                        "constrained_columns": fk.get("constrained_columns", []),
                        "referred_schema": fk.get("referred_schema"),
                        "referred_table": fk.get("referred_table"),
                        "referred_columns": fk.get("referred_columns", []),
                    }
                )
        except Exception:
            pass

    qualified_name = f"{schema}.{table_name}" if schema else table_name
    return {
        "name": table_name,
        "schema": schema,
        "qualified_name": qualified_name,
        "type": item_type,
        "columns": columns_info,
        "primary_keys": sorted(pk_columns),
        "foreign_keys": foreign_keys_info,
    }


def extract_schema(connection_target: str, schema_name: str | None = None) -> dict[str, Any]:
    """
    Step 1: Verifies that the target database exists / is reachable and extracts its complete schema.
    """
    resolved = resolve_target(connection_target)
    if not resolved.exists:
        return {
            "exists": False,
            "dialect": resolved.dialect,
            "target": resolved.masked_target or connection_target,
            "error": resolved.error,
            "next_step": "Verify the database path, URI, or .env profile name and try again.",
        }

    engine: Engine | None = None
    try:
        engine = create_readonly_engine(resolved)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        inspector = inspect(engine)
        dialect_name = engine.dialect.name
        default_schema = inspector.default_schema_name

        # Determine which schemas to inspect
        schemas_to_inspect: list[str | None] = []
        available_schemas: list[str] = []
        try:
            available_schemas = [
                s
                for s in inspector.get_schema_names()
                if s.lower()
                not in (
                    "information_schema",
                    "sys",
                    "pg_catalog",
                    "pg_toast",
                    "performance_schema",
                    "mysql",
                    "db_owner",
                    "db_accessadmin",
                    "db_securityadmin",
                    "db_ddladmin",
                    "db_backupoperator",
                    "db_datareader",
                    "db_datawriter",
                    "db_denydatareader",
                    "db_denydatawriter",
                    "guest",
                )
            ]
        except Exception:
            available_schemas = []

        if schema_name and schema_name.strip():
            schemas_to_inspect = [schema_name.strip()]
        elif dialect_name == "sqlite":
            schemas_to_inspect = [None]
        elif available_schemas:
            schemas_to_inspect = available_schemas
        else:
            schemas_to_inspect = [default_schema]

        tables: list[dict[str, Any]] = []
        views: list[dict[str, Any]] = []

        for current_schema in schemas_to_inspect:
            try:
                table_names = inspector.get_table_names(schema=current_schema)
            except Exception:
                table_names = []

            for tbl in table_names:
                if dialect_name == "sqlite" and tbl.startswith("sqlite_"):
                    continue
                tables.append(_build_table_metadata(inspector, tbl, current_schema, "table"))

            try:
                view_names = inspector.get_view_names(schema=current_schema)
            except Exception:
                view_names = []

            for vw in view_names:
                views.append(_build_table_metadata(inspector, vw, current_schema, "view"))

        return {
            "exists": True,
            "dialect": dialect_name,
            "dialect_hint": DIALECT_HINTS.get(dialect_name, "Use standard ANSI SQL SELECT queries."),
            "target": resolved.masked_target,
            "resolved_from_env": resolved.resolved_from_env,
            "default_schema": default_schema,
            "available_schemas": available_schemas,
            "table_count": len(tables),
            "view_count": len(views),
            "tables": tables,
            "views": views,
            "next_step": (
                "Now construct a read-only SQL query matching the dialect and exact table/column names above, "
                "and call `execute_query`."
            ),
        }
    except ModuleNotFoundError as exc:
        return {
            "exists": False,
            "dialect": resolved.dialect,
            "target": resolved.masked_target,
            "error": (
                f"Database driver missing for dialect '{resolved.dialect}': {exc}. "
                "Install optional drivers via `pip install -e .[postgres]` or `pip install -e .[mysql]`."
            ),
        }
    except SQLAlchemyError as exc:
        return {
            "exists": False,
            "dialect": resolved.dialect,
            "target": resolved.masked_target,
            "error": f"Database connection or inspection failed: {exc}",
        }
    except Exception as exc:
        return {
            "exists": False,
            "dialect": resolved.dialect,
            "target": resolved.masked_target,
            "error": f"Unexpected error while inspecting database: {exc}",
        }
    finally:
        if engine is not None:
            engine.dispose()


def run_readonly_query(
    connection_target: str,
    sql_query: str,
    max_rows: int = 100,
) -> dict[str, Any]:
    """
    Step 2: Validates and executes a read-only SQL query against the target database.
    """
    # Clamp max_rows to a safe range (1..1000)
    effective_max_rows = max(1, min(int(max_rows or 100), 1000))

    is_valid, validation_error = validate_readonly_sql(sql_query)
    if not is_valid:
        return {
            "success": False,
            "error": validation_error,
            "query": sql_query,
        }

    resolved = resolve_target(connection_target)
    if not resolved.exists:
        return {
            "success": False,
            "dialect": resolved.dialect,
            "target": resolved.masked_target or connection_target,
            "error": resolved.error,
            "hint": "Call `inspect_database` first to verify that the database exists and inspect its schema.",
        }

    engine: Engine | None = None
    try:
        engine = create_readonly_engine(resolved)
        with engine.connect() as conn:
            if resolved.dialect == "postgresql":
                conn = conn.execution_options(postgresql_readonly=True)

            result = conn.execute(text(sql_query))
            if not result.returns_rows:
                return {
                    "success": True,
                    "dialect": engine.dialect.name,
                    "target": resolved.masked_target,
                    "query": sql_query,
                    "columns": [],
                    "rows": [],
                    "row_count": 0,
                    "truncated": False,
                }

            columns = list(result.keys())
            fetched_rows = result.fetchmany(effective_max_rows + 1)
            truncated = len(fetched_rows) > effective_max_rows
            if truncated:
                fetched_rows = fetched_rows[:effective_max_rows]

            serialized_rows = [
                {col: _serialize_value(val) for col, val in zip(columns, row)}
                for row in fetched_rows
            ]

            return {
                "success": True,
                "dialect": engine.dialect.name,
                "target": resolved.masked_target,
                "query": sql_query,
                "columns": columns,
                "row_count": len(serialized_rows),
                "max_rows": effective_max_rows,
                "truncated": truncated,
                "rows": serialized_rows,
            }
    except SQLAlchemyError as exc:
        return {
            "success": False,
            "dialect": resolved.dialect,
            "target": resolved.masked_target,
            "query": sql_query,
            "error": f"SQL execution error: {exc}",
            "hint": (
                "Ensure you called `inspect_database` first and used exact table/column names "
                f"and syntax valid for dialect '{resolved.dialect}'."
            ),
        }
    except Exception as exc:
        return {
            "success": False,
            "dialect": resolved.dialect,
            "target": resolved.masked_target,
            "query": sql_query,
            "error": f"Unexpected error during query execution: {exc}",
        }
    finally:
        if engine is not None:
            engine.dispose()
