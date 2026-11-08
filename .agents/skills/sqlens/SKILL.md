---
name: sqlens
description: Safe, strictly read-only inspection of SQLite, SQL Server (MSSQL), PostgreSQL, and MySQL databases using the sqlens MCP server. Always activate this skill whenever the user provides a database file path, connection URI, ODBC string, or .env profile name and asks to inspect schema or query data.
---

# SQLens — Database Inspection Workflow (SQLite, SQL Server, PostgreSQL, MySQL)

Whenever the user provides a database target (e.g., a `.db` / `.sqlite` file path, an ODBC connection string, a database URI, or a `.env` profile name) and describes what they want to check, you **MUST** strictly follow this 3-step sequence.

## Step 1: Verify Existence & Inspect Schema (MANDATORY FIRST STEP)
1. **Always start** by calling `inspect_database(connection_target=...)`.
2. **Never guess**: Do NOT call `execute_query` blindly and do NOT guess table or column names before calling `inspect_database`.
3. Check the `exists` field in the response:
   - If `exists: false` — **stop immediately** and report the error to the user (e.g., that the database file does not exist at the given path or the SQL server is unreachable). Do not attempt to run any SQL queries.
   - If `exists: true` — review the `dialect` (`sqlite`, `mssql`, `postgresql`, `mysql`) along with `tables` and `views` (table names, schemas, column names, data types, `primary_keys`, and `foreign_keys`).

## Step 2: Translate User Intent into a Dialect-Aware Read-Only SQL Query
Based on the schema and `dialect` returned in Step 1, translate the user's intent into a single read-only SQL query (`SELECT` or `WITH ... SELECT`):
- **For SQL Server (`dialect == "mssql"`)**:
  - Use `SELECT TOP N ...` instead of `LIMIT N` (or `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY` when paired with `ORDER BY`).
  - Include the schema name (e.g., `dbo.TableName` or `[dbo].[TableName]`).
  - Use square brackets `[ColumnName]` for identifiers containing spaces or reserved keywords.
- **For SQLite (`dialect == "sqlite"`), PostgreSQL (`dialect == "postgresql"`), MySQL (`dialect == "mysql"`)**:
  - Use `LIMIT N` at the end of the query.
- Use only exact table and column names verified by `inspect_database`.
- Never generate data-modifying queries (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `CREATE`, `EXEC`, `SELECT ... INTO`).

## Step 3: Execute Query & Present Results
1. Call `execute_query(connection_target=..., sql_query=..., max_rows=...)`.
2. If the query returns a syntax error, analyze the error against the schema from Step 1, fix the query, and call `execute_query` again.
3. Present a clear summary of the results (e.g., as a Markdown table) along with the exact SQL query that was executed.
