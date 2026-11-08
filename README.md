# SQLens — Multi-DB Read-Only Inspection MCP Server

[![CI](https://github.com/pawelworyna/sqlens/actions/workflows/ci.yml/badge.svg)](https://github.com/pawelworyna/sqlens/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**SQLens** is a Python Model Context Protocol (MCP) server designed for safe, strictly **read-only** inspection of **SQLite**, **SQL Server (MSSQL)**, **PostgreSQL**, and **MySQL / MariaDB** databases.

It enforces a deterministic 3-step workflow for AI coding agents:
1. **`inspect_database`**: Verifies whether the database file exists (or the SQL server is reachable), detects the SQL dialect (`sqlite`, `mssql`, `postgresql`, `mysql`), and extracts the full database schema (tables, views, columns, data types, primary keys, and foreign keys).
2. **Dialect-Aware SQL Generation**: The LLM translates the user's natural-language intent into a valid read-only SQL query tailored to the discovered schema and dialect (e.g., `SELECT TOP N` for T-SQL / SQL Server vs. `LIMIT N` for SQLite / PostgreSQL / MySQL).
3. **`execute_query`**: Validates that the query is strictly read-only (`SELECT`, `WITH`, `EXPLAIN`, `PRAGMA`, `SHOW`) and executes it safely with row limits and automatic JSON serialization.

---

## Key Features

- **Multi-Database Support**:
  - **SQLite**: Validates file existence and checks the 16-byte SQLite header before connecting via `?mode=ro&uri=true` + `PRAGMA query_only = ON` (never creates empty files when given a non-existent path).
  - **SQL Server (MSSQL)**: Built-in support for both raw ODBC connection strings (`pyodbc` with `ApplicationIntent=ReadOnly`) and direct TDS URIs (`pymssql`).
  - **PostgreSQL & MySQL**: Ready out-of-the-box via SQLAlchemy optional extras (`pip install -e ".[postgres]"` / `pip install -e ".[mysql]"`).
- **Strict Read-Only Guardrails**: Blocks `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `CREATE`, `EXEC`, `SELECT ... INTO`, modifying `PRAGMA`s, and stacked semicolon-separated statements.
- **`.env` Profile Resolution & Password Masking**: Reference database profiles by name (e.g., `MSSQL_LOCAL`) directly in your prompt without exposing credentials in chat history.
- **Cross-Agent Compatibility**: Clean `stdio` JSON-RPC stream, flat JSON Schema tool parameters, `ToolAnnotations(readOnlyHint=True)`, and built-in instruction files for **GitHub Copilot (VS Code & CLI)**, **Antigravity**, **OpenAI Codex CLI**, and **Hermes**.

---

## Installation

Clone the repository and install it in a virtual environment:

```powershell
git clone https://github.com/pawelworyna/sqlens.git
cd sqlens

# Create a virtual environment
python -m venv .venv

# Install SQLens (includes SQLite + SQL Server support + test suite)
.\.venv\Scripts\pip install -e ".[dev]"

# OPTIONAL: Install with PostgreSQL and MySQL drivers
.\.venv\Scripts\pip install -e ".[all,dev]"
```

*(Optional)* If you connect to **SQL Server**, **PostgreSQL**, or **MySQL**, copy [`.env.example`](.env.example) to `.env` in the repository root to define named connection profiles so you don't need to paste passwords in prompts:

```env
MSSQL_LOCAL="Driver={ODBC Driver 18 for SQL Server};Server=localhost;Database=MyDatabase;Trusted_Connection=yes;TrustServerCertificate=yes;"
MSSQL_PROD="mssql+pymssql://username:password@10.0.0.5:1433/ERP"
```

---

## Setup Across AI Environments

> **Note**: In the configurations below, replace `C:/path/to/sqlens` with the actual path to your cloned `sqlens` repository.

### 1. GitHub Copilot in VS Code

#### A. Workspace Configuration (Included)
This repository already includes [`.vscode/mcp.json`](.vscode/mcp.json) and [`.github/copilot-instructions.md`](.github/copilot-instructions.md).
1. Open the repository folder in VS Code.
2. Open **GitHub Copilot Chat** (`Ctrl+Alt+I`) and switch to **Agent Mode**.
3. Click the Tools icon (🔧) in the chat input — you will see **`sqlens`** with `inspect_database` and `execute_query`.

#### B. Global Configuration (Use in Any Project)
1. Press `Ctrl+Shift+P` -> select **MCP: Open User Configuration** (or open your global `settings.json`).
2. Add the server definition:
```json
{
  "mcp": {
    "servers": {
      "sqlens": {
        "type": "stdio",
        "command": "C:/path/to/sqlens/.venv/Scripts/python.exe",
        "args": ["-m", "sqlens"],
        "env": {
          "PYTHONUTF8": "1"
        }
      }
    }
  }
}
```

---

### 2. GitHub Copilot CLI (`copilot`)

**GitHub Copilot Coding Agent CLI** supports MCP servers and automatically loads [`AGENTS.md`](AGENTS.md) and [`.github/copilot-instructions.md`](.github/copilot-instructions.md).

1. Add `sqlens` to your global Copilot CLI MCP configuration (`~/.copilot/mcp-config.json`):
```json
{
  "mcpServers": {
    "sqlens": {
      "type": "local",
      "command": "C:/path/to/sqlens/.venv/Scripts/python.exe",
      "args": ["-m", "sqlens"],
      "env": {
        "PYTHONUTF8": "1"
      }
    }
  }
}
```
2. Alternatively, register it interactively inside `copilot` CLI using `/mcp add`:
   - **Name**: `sqlens`
   - **Command**: `C:/path/to/sqlens/.venv/Scripts/python.exe -m sqlens`

---

### 3. Antigravity

This project includes a ready-to-use Skill at [`.agents/skills/sqlens/SKILL.md`](.agents/skills/sqlens/SKILL.md) and workspace rules in [`AGENTS.md`](AGENTS.md).

1. Add `sqlens` to your Antigravity MCP configuration (`~/.gemini/antigravity/mcp_config.json`):
```json
{
  "mcpServers": {
    "sqlens": {
      "command": "C:/path/to/sqlens/.venv/Scripts/python.exe",
      "args": ["-m", "sqlens"],
      "env": {
        "PYTHONUTF8": "1"
      }
    }
  }
}
```
2. *(Optional — Global Skill)* To make the `sqlens` workflow skill available across all workspaces in Antigravity, copy `.agents/skills/sqlens` to your global skills directory:
```powershell
Copy-Item -Recurse -Force ".\.agents\skills\sqlens" "$HOME\.gemini\antigravity\skills\sqlens"
```

---

### 4. OpenAI Codex CLI (`codex`)

Codex CLI natively supports MCP servers in `~/.codex/config.toml` and automatically reads instructions from [`AGENTS.md`](AGENTS.md) (as well as `~/.codex/AGENTS.md`).

1. Open (or create) `~/.codex/config.toml` and add:
```toml
[mcp_servers.sqlens]
command = 'C:/path/to/sqlens/.venv/Scripts/python.exe'
args = ["-m", "sqlens"]
env = { "PYTHONUTF8" = "1" }
startup_timeout_sec = 15
tool_timeout_sec = 60
```
2. *(Alternative via CLI)* Register the server directly from the terminal:
```powershell
codex mcp add sqlens -- C:/path/to/sqlens/.venv/Scripts/python.exe -m sqlens
```
3. *(Optional — Global Instructions)* To enforce the `inspect_database` -> `execute_query` sequence in any directory, append the contents of [`AGENTS.md`](AGENTS.md) to `~/.codex/AGENTS.md`.

---

### 5. Hermes (`hermes-agent`)

Hermes supports MCP servers over `stdio` as well as `SKILL.md` skills.

1. Open your Hermes configuration file (`~/.hermes/config.yaml`) and add `sqlens` under `mcp_servers`:
```yaml
mcp_servers:
  sqlens:
    command: "C:/path/to/sqlens/.venv/Scripts/python.exe"
    args:
      - "-m"
      - "sqlens"
    env:
      PYTHONUTF8: "1"
```
2. Copy [`.agents/skills/sqlens/SKILL.md`](.agents/skills/sqlens/SKILL.md) to your global Hermes skills folder (`~/.hermes/skills/sqlens/SKILL.md`):
```powershell
New-Item -ItemType Directory -Force -Path "$HOME\.hermes\skills\sqlens"
Copy-Item -Force ".\.agents\skills\sqlens\SKILL.md" "$HOME\.hermes\skills\sqlens\SKILL.md"
```

---

## Usage Examples in Prompts

Regardless of whether you use **GitHub Copilot**, **Antigravity**, **Codex**, or **Hermes**, simply provide the `connection_target` (file path, `.env` profile name, ODBC string, or URI) and describe what you want to check:

- **SQLite (file path)**:
  > *"Check the database at `C:/data/shop.db`, list its tables, and show the top 5 customers by total order amount."*

- **SQL Server (via `.env` profile name)**:
  > *"In database `MSSQL_LOCAL`, inspect the invoice tables and list the 10 most recent unpaid invoices."*

- **SQL Server (via direct URI or ODBC string)**:
  > *"Check `mssql+pymssql://sa:Pass123@localhost:1433/Inventory` for products where stock quantity is below 5."*

- **PostgreSQL / MySQL**:
  > *"Inspect `postgresql://postgres:secret@localhost:5432/analytics` and count new user signups per day over the last 7 days."*

### What Happens Under the Hood:
1. The agent calls **`inspect_database(connection_target=...)`** first to verify that the database exists, check its SQL dialect (`sqlite`, `mssql`, `postgresql`, `mysql`), and inspect all tables, columns, primary keys, and foreign keys.
2. The agent crafts a read-only `SELECT` query matching the exact schema and dialect (e.g., `SELECT TOP 10` for SQL Server vs. `LIMIT 5` for SQLite).
3. The agent calls **`execute_query(connection_target=..., sql_query=...)`** and presents the results clearly.

---

## Running Tests

```powershell
.\.venv\Scripts\pytest -v
```

## License

[MIT](LICENSE)
