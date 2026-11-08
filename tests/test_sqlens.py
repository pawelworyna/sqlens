"""Comprehensive unit tests for SQLens MCP server, target resolver, schema inspector, and read-only SQL executor."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from sqlens.db import extract_schema, run_readonly_query, validate_readonly_sql
from sqlens.resolver import resolve_target
from sqlens.server import execute_query, inspect_database, mcp


@pytest.fixture()
def sample_sqlite_db(tmp_path: Path) -> Path:
    """Creates a temporary SQLite database with tables, a view, primary keys, foreign keys, and sample data."""
    db_path = tmp_path / "shop.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            city TEXT DEFAULT 'Warszawa'
        );

        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            total_amount NUMERIC(10, 2) NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );

        CREATE VIEW customer_order_summary AS
        SELECT
            c.id AS customer_id,
            c.name AS customer_name,
            COUNT(o.id) AS orders_count,
            COALESCE(SUM(o.total_amount), 0) AS total_spent
        FROM customers c
        LEFT JOIN orders o ON o.customer_id = c.id
        GROUP BY c.id, c.name;

        INSERT INTO customers (name, email, city) VALUES
            ('Anna Kowalska', 'anna@example.com', 'Warszawa'),
            ('Jan Nowak', 'jan@example.com', 'Krakow'),
            ('Piotr Wisniewski', 'piotr@example.com', 'Gdansk');

        INSERT INTO orders (customer_id, total_amount, created_at) VALUES
            (1, 150.50, '2026-10-01'),
            (1, 299.99, '2026-10-15'),
            (2, 89.00, '2026-10-18');
        """
    )
    conn.commit()
    conn.close()
    return db_path


def test_missing_sqlite_file_does_not_create_file(tmp_path: Path) -> None:
    """Verifies that inspecting or querying a non-existent file returns exists=False without creating it."""
    missing_path = tmp_path / "does_not_exist.db"
    assert not missing_path.exists()

    schema_result = inspect_database(str(missing_path))
    assert schema_result["exists"] is False
    assert "does not exist" in schema_result["error"]
    assert not missing_path.exists()

    query_result = execute_query(str(missing_path), "SELECT 1")
    assert query_result["success"] is False
    assert not missing_path.exists()


def test_invalid_file_header_is_rejected(tmp_path: Path) -> None:
    """Verifies that a regular text file is rejected as not a valid SQLite database."""
    fake_db = tmp_path / "not_a_db.db"
    fake_db.write_text("This is a plain text file, not SQLite!", encoding="utf-8")

    result = inspect_database(str(fake_db))
    assert result["exists"] is False
    assert "not a valid SQLite 3 database" in result["error"]


def test_resolver_supports_mssql_postgres_mysql_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests target resolution for ODBC strings, URIs, and .env profile names."""
    # 1. Raw ODBC string for SQL Server
    odbc = "Driver={ODBC Driver 18 for SQL Server};Server=myserver;Database=mydb;UID=sa;PWD=secret123;"
    res_odbc = resolve_target(odbc)
    assert res_odbc.exists is True
    assert res_odbc.dialect == "mssql"
    assert res_odbc.sqlalchemy_url.startswith("mssql+pyodbc:///?odbc_connect=")
    assert "ApplicationIntent%3DReadOnly" in res_odbc.sqlalchemy_url
    assert "secret123" not in res_odbc.masked_target
    assert "***" in res_odbc.masked_target

    # 2. SQL Server URI
    res_mssql = resolve_target("sqlserver://admin:topsecret@10.0.0.5:1433/sales")
    assert res_mssql.exists is True
    assert res_mssql.dialect == "mssql"
    assert res_mssql.sqlalchemy_url == "mssql+pymssql://admin:topsecret@10.0.0.5:1433/sales"
    assert "topsecret" not in res_mssql.masked_target

    # 3. PostgreSQL URI
    res_pg = resolve_target("postgres://pguser:pgpass@localhost:5432/analytics")
    assert res_pg.exists is True
    assert res_pg.dialect == "postgresql"
    assert res_pg.sqlalchemy_url == "postgresql+psycopg://pguser:pgpass@localhost:5432/analytics"
    assert "pgpass" not in res_pg.masked_target

    # 4. MySQL URI
    res_mysql = resolve_target("mysql://root:mysqlpass@localhost:3306/shop")
    assert res_mysql.exists is True
    assert res_mysql.dialect == "mysql"
    assert res_mysql.sqlalchemy_url == "mysql+pymysql://root:mysqlpass@localhost:3306/shop"
    assert "mysqlpass" not in res_mysql.masked_target

    # 5. Profile from environment variable
    monkeypatch.setenv("PROD_MSSQL", "mssql+pymssql://reader:pw123@db.internal:1433/erp")
    res_env = resolve_target("PROD_MSSQL")
    assert res_env.exists is True
    assert res_env.resolved_from_env is True
    assert res_env.dialect == "mssql"
    assert "pw123" not in res_env.masked_target


def test_inspect_database_extracts_full_schema(sample_sqlite_db: Path) -> None:
    """Verifies that inspect_database returns tables, views, columns, primary keys, and foreign keys."""
    result = inspect_database(str(sample_sqlite_db))
    assert result["exists"] is True
    assert result["dialect"] == "sqlite"
    assert result["table_count"] == 2
    assert result["view_count"] == 1

    tables_by_name = {t["name"]: t for t in result["tables"]}
    assert "customers" in tables_by_name
    assert "orders" in tables_by_name

    customers_table = tables_by_name["customers"]
    assert customers_table["primary_keys"] == ["id"]
    col_names = [c["name"] for c in customers_table["columns"]]
    assert col_names == ["id", "name", "email", "city"]

    orders_table = tables_by_name["orders"]
    assert len(orders_table["foreign_keys"]) == 1
    fk = orders_table["foreign_keys"][0]
    assert fk["constrained_columns"] == ["customer_id"]
    assert fk["referred_table"] == "customers"
    assert fk["referred_columns"] == ["id"]

    views_by_name = {v["name"]: v for v in result["views"]}
    assert "customer_order_summary" in views_by_name


def test_execute_query_select_and_truncation(sample_sqlite_db: Path) -> None:
    """Verifies read-only SELECT and CTE queries as well as max_rows truncation."""
    res = execute_query(
        str(sample_sqlite_db),
        "SELECT customer_name, orders_count, total_spent FROM customer_order_summary ORDER BY total_spent DESC",
    )
    assert res["success"] is True
    assert res["row_count"] == 3
    assert res["truncated"] is False
    assert res["columns"] == ["customer_name", "orders_count", "total_spent"]
    assert res["rows"][0]["customer_name"] == "Anna Kowalska"
    assert res["rows"][0]["orders_count"] == 2

    # Test max_rows truncation
    res_trunc = execute_query(
        str(sample_sqlite_db),
        "SELECT * FROM customers ORDER BY id",
        max_rows=2,
    )
    assert res_trunc["success"] is True
    assert res_trunc["row_count"] == 2
    assert res_trunc["truncated"] is True


@pytest.mark.parametrize(
    "malicious_sql",
    [
        "DROP TABLE customers",
        "DELETE FROM customers WHERE id = 1",
        "UPDATE customers SET name = 'Hacked' WHERE id = 1",
        "INSERT INTO customers (name, email) VALUES ('X', 'x@example.com')",
        "SELECT * FROM customers; DROP TABLE customers;",
        "SELECT * INTO new_table FROM customers",
        "EXEC sp_who",
        "PRAGMA writable_schema = 1",
        "WITH cte AS (SELECT 1) DELETE FROM customers",
    ],
)
def test_readonly_sql_validator_blocks_modifying_queries(sample_sqlite_db: Path, malicious_sql: str) -> None:
    """Ensures all modifying or stacked SQL statements are rejected before touching the database."""
    is_valid, error = validate_readonly_sql(malicious_sql)
    assert is_valid is False
    assert error != ""

    res = execute_query(str(sample_sqlite_db), malicious_sql)
    assert res["success"] is False


def test_mcp_tool_schemas_are_compatible_with_copilot_codex_antigravity_hermes() -> None:
    """
    Verifies that FastMCP tools expose clean JSON schemas (no nullable anyOf unions)
    and include readOnlyHint=True annotations for GitHub Copilot, Codex, Antigravity, and Hermes.
    """
    tools = asyncio.run(mcp.list_tools())
    tool_map = {t.name: t for t in tools}

    assert "inspect_database" in tool_map
    assert "execute_query" in tool_map

    for tool_name, tool in tool_map.items():
        # Verify readOnlyHint annotation
        assert tool.annotations is not None, f"{tool_name} is missing ToolAnnotations"
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False

        # Verify flat parameter schema (no complex anyOf required for basic arguments)
        properties = tool.inputSchema.get("properties", {})
        for prop_name, prop_schema in properties.items():
            assert "type" in prop_schema, f"Property {prop_name} in {tool_name} should have a direct 'type'"
            assert prop_schema["type"] in ("string", "integer", "boolean", "number")
