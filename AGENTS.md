# AI Agent Instructions (Codex, GitHub Copilot, Antigravity, Hermes)

This environment provides the **`sqlens`** MCP server for safe, strictly read-only inspection of **SQLite**, **SQL Server (MSSQL)**, **PostgreSQL**, and **MySQL** databases.

## Mandatory Database Workflow (`sqlens`)

Whenever the user provides a database file path (e.g., `C:/.../db.sqlite`), an ODBC connection string, a URI, or a `.env` profile name and describes what they want to inspect or query:

1. **STEP 1 — Verify Existence & Retrieve Schema (`inspect_database`)**:
   - **ALWAYS** start by calling `inspect_database(connection_target=...)`.
   - Never call `execute_query` before inspecting the schema via `inspect_database`.
   - If `inspect_database` returns `"exists": false`, stop immediately and inform the user that the database does not exist or cannot be reached.

2. **STEP 2 — Construct a Dialect-Specific Read-Only SQL Query**:
   - Check the `"dialect"` field returned by `inspect_database`:
     - **`mssql` (SQL Server)**: use T-SQL syntax (`SELECT TOP N ...`, `[schema].[table]`, e.g., `dbo.Users`). Do not use `LIMIT`.
     - **`sqlite` / `postgresql` / `mysql`**: use `LIMIT N`.
   - Use only the exact table, view, column, and foreign-key names discovered via `inspect_database`.
   - Only read-only queries (`SELECT`, `WITH`, `EXPLAIN`, `PRAGMA`, `SHOW`) are permitted.

3. **STEP 3 — Execute Query (`execute_query`)**:
   - Call `execute_query(connection_target=..., sql_query=...)`.
   - Present the results clearly and show the executed SQL query.
