# GitHub Copilot Instructions — SQLens Database Inspection

When the user asks to inspect, check, or query any database (by file path like `.db`/`.sqlite`, SQL Server connection string, URI, or `.env` profile name) using the `sqlens` MCP server, always follow this strict 3-step sequence:

1. **Verify Existence & Inspect Schema First (`inspect_database`)**:
   - ALWAYS call `inspect_database(connection_target=...)` first.
   - Do NOT guess table or column names and do NOT call `execute_query` before calling `inspect_database`.
   - If `exists` is `false`, immediately report the error to the user and stop.

2. **Build Dialect-Aware Read-Only SQL**:
   - Use the `dialect`, `tables`, `views`, `columns`, `primary_keys`, and `foreign_keys` returned by `inspect_database`.
   - If `dialect` is `"mssql"` (SQL Server): use T-SQL syntax (`SELECT TOP N`, `[schema].[table]`).
   - If `dialect` is `"sqlite"`, `"postgresql"`, or `"mysql"`: use `LIMIT N`.
   - Generate strictly read-only queries (`SELECT` / `WITH`).

3. **Execute Query (`execute_query`)**:
   - Call `execute_query(connection_target=..., sql_query=...)` with the constructed SQL query.
   - Present the results clearly along with the executed SQL query.
