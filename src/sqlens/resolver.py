"""Connection target resolution and validation for SQLite, SQL Server, PostgreSQL, and MySQL."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus, urlsplit, urlunsplit

from dotenv import load_dotenv

# Load .env from project root and current working directory without writing anything to stdout
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env", override=False)
load_dotenv(Path.cwd() / ".env", override=False)

SQLITE_HEADER = b"SQLite format 3\x00"

DIALECT_HINTS: dict[str, str] = {
    "sqlite": (
        "SQLite dialect: use `LIMIT N` to restrict rows, backticks or double quotes for identifiers, "
        "and `sqlite_master` / `PRAGMA` for metadata."
    ),
    "mssql": (
        "SQL Server (T-SQL) dialect: use `SELECT TOP N ...` instead of `LIMIT N` (unless using OFFSET/FETCH with ORDER BY), "
        "use square brackets `[schema].[table]` for identifiers, and include schema name (e.g. `dbo.TableName`)."
    ),
    "postgresql": (
        "PostgreSQL dialect: use `LIMIT N`, double quotes `\"schema\".\"table\"` for case-sensitive identifiers, "
        "and default schema is usually `public`."
    ),
    "mysql": (
        "MySQL / MariaDB dialect: use `LIMIT N` and backticks `` `table`.`column` `` for identifiers."
    ),
}


@dataclass(frozen=True)
class ResolvedTarget:
    """Represents a validated and normalized database connection target."""

    original_target: str
    resolved_from_env: bool
    dialect: str  # 'sqlite', 'mssql', 'postgresql', 'mysql'
    sqlalchemy_url: str
    masked_target: str
    exists: bool
    error: str = ""
    sqlite_path: Path | None = None


def _mask_url_password(url: str) -> str:
    """Masks password in URI or ODBC connection string for safe display."""
    # Mask ODBC Password / PWD
    masked = re.sub(
        r"(?i)(\b(?:pwd|password)\s*=\s*)([^;]+)",
        r"\1***",
        url,
    )
    if "://" in masked:
        try:
            parts = urlsplit(masked)
            if parts.password:
                netloc = parts.netloc.replace(f":{parts.password}@", ":***@")
                masked = urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
        except Exception:
            pass
    return masked


def _looks_like_odbc_string(target: str) -> bool:
    """Checks if the target is a raw ODBC connection string (e.g., for SQL Server)."""
    lowered = target.lower()
    return (
        ";" in target
        and "://" not in target
        and any(
            key in lowered
            for key in ("driver=", "server=", "data source=", "dsn=", "trusted_connection=", "uid=")
        )
    )


def _validate_sqlite_file(file_path: Path, original_target: str, resolved_from_env: bool) -> ResolvedTarget:
    """Validates that a local SQLite database file exists and has a valid SQLite header."""
    try:
        expanded = file_path.expanduser()
        resolved_path = expanded.resolve()
    except Exception as exc:
        return ResolvedTarget(
            original_target=original_target,
            resolved_from_env=resolved_from_env,
            dialect="sqlite",
            sqlalchemy_url="",
            masked_target=str(file_path),
            exists=False,
            error=f"Invalid file path '{file_path}': {exc}",
        )

    if not resolved_path.exists():
        return ResolvedTarget(
            original_target=original_target,
            resolved_from_env=resolved_from_env,
            dialect="sqlite",
            sqlalchemy_url="",
            masked_target=str(resolved_path),
            exists=False,
            error=f"Database file does not exist at path: '{resolved_path}'",
            sqlite_path=resolved_path,
        )

    if not resolved_path.is_file():
        return ResolvedTarget(
            original_target=original_target,
            resolved_from_env=resolved_from_env,
            dialect="sqlite",
            sqlalchemy_url="",
            masked_target=str(resolved_path),
            exists=False,
            error=f"Path exists but is not a file (it may be a directory): '{resolved_path}'",
            sqlite_path=resolved_path,
        )

    # Check SQLite 16-byte magic header (empty 0-byte file is also accepted by SQLite as an empty DB)
    try:
        file_size = resolved_path.stat().st_size
        if file_size > 0:
            with resolved_path.open("rb") as fh:
                header = fh.read(16)
            if header != SQLITE_HEADER:
                return ResolvedTarget(
                    original_target=original_target,
                    resolved_from_env=resolved_from_env,
                    dialect="sqlite",
                    sqlalchemy_url="",
                    masked_target=str(resolved_path),
                    exists=False,
                    error=(
                        f"File exists at '{resolved_path}', but it is not a valid SQLite 3 database "
                        "(invalid file header)."
                    ),
                    sqlite_path=resolved_path,
                )
    except OSError as exc:
        return ResolvedTarget(
            original_target=original_target,
            resolved_from_env=resolved_from_env,
            dialect="sqlite",
            sqlalchemy_url="",
            masked_target=str(resolved_path),
            exists=False,
            error=f"Cannot read database file '{resolved_path}': {exc}",
            sqlite_path=resolved_path,
        )

    posix_path = resolved_path.as_posix()
    sqlalchemy_url = f"sqlite:///file:{posix_path}?mode=ro&uri=true"
    return ResolvedTarget(
        original_target=original_target,
        resolved_from_env=resolved_from_env,
        dialect="sqlite",
        sqlalchemy_url=sqlalchemy_url,
        masked_target=str(resolved_path),
        exists=True,
        sqlite_path=resolved_path,
    )


def resolve_target(connection_target: str) -> ResolvedTarget:
    """
    Resolves a user-provided connection_target into a normalized SQLAlchemy URL and dialect.

    Supports:
    1. Environment variable profile names (e.g., 'MSSQL_LOCAL', 'SQLENS_PROD')
    2. Local SQLite file paths (e.g., 'C:/data/app.db', './mydb.sqlite')
    3. Raw SQL Server ODBC connection strings (e.g., 'Driver={ODBC Driver 18 for SQL Server};Server=...')
    4. SQLAlchemy / DB URIs ('sqlite://...', 'mssql://...', 'sqlserver://...', 'postgresql://...', 'mysql://...')
    """
    raw = (connection_target or "").strip()
    if not raw:
        return ResolvedTarget(
            original_target=connection_target,
            resolved_from_env=False,
            dialect="unknown",
            sqlalchemy_url="",
            masked_target="",
            exists=False,
            error="Empty `connection_target` provided. Provide a file path, URI, ODBC string, or .env profile name.",
        )

    # 1. Check if raw string matches an environment variable name (or SQLENS_<NAME>)
    resolved_from_env = False
    target = raw
    if raw in os.environ and os.environ[raw].strip():
        target = os.environ[raw].strip()
        resolved_from_env = True
    elif f"SQLENS_{raw}" in os.environ and os.environ[f"SQLENS_{raw}"].strip():
        target = os.environ[f"SQLENS_{raw}"].strip()
        resolved_from_env = True

    # Strip surrounding quotes if present in .env or user prompt
    if len(target) >= 2 and target[0] == target[-1] and target[0] in ("'", '"'):
        target = target[1:-1].strip()

    # 2. Check if it is an ODBC connection string (SQL Server)
    if _looks_like_odbc_string(target):
        odbc_str = target
        if "applicationintent=" not in odbc_str.lower():
            odbc_str = odbc_str.rstrip(";") + ";ApplicationIntent=ReadOnly;"
        encoded = quote_plus(odbc_str)
        url = f"mssql+pyodbc:///?odbc_connect={encoded}"
        return ResolvedTarget(
            original_target=raw,
            resolved_from_env=resolved_from_env,
            dialect="mssql",
            sqlalchemy_url=url,
            masked_target=_mask_url_password(target),
            exists=True,
        )

    # 3. Check if it is a URI scheme (e.g. sqlite://, mssql://, postgresql://, mysql://)
    # Note: Windows drive letters like "C:\..." or "C:/..." have a single character before ':'
    scheme_match = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]+)://(.*)$", target)
    if scheme_match:
        scheme = scheme_match.group(1).lower()
        rest = scheme_match.group(2)

        if scheme.startswith("sqlite"):
            # Handle sqlite:///path/to/file.db
            path_part = rest
            if path_part.startswith("/"):
                # On Windows sqlite:///C:/path/to/db has a leading slash before drive letter
                if re.match(r"^/[a-zA-Z]:[/\\]", path_part):
                    path_part = path_part[1:]
                elif path_part.startswith("//"):
                    path_part = path_part[1:]
            path_part = path_part.split("?")[0]
            return _validate_sqlite_file(Path(path_part), raw, resolved_from_env)

        if scheme in ("mssql", "sqlserver", "mssql+pymssql", "mssql+pyodbc"):
            if scheme in ("mssql", "sqlserver"):
                # Default to pymssql for standard URI unless odbc_connect is in query
                driver_scheme = "mssql+pyodbc" if "odbc_connect=" in rest.lower() or "driver=" in rest.lower() else "mssql+pymssql"
                normalized_url = f"{driver_scheme}://{rest}"
            else:
                normalized_url = target
            return ResolvedTarget(
                original_target=raw,
                resolved_from_env=resolved_from_env,
                dialect="mssql",
                sqlalchemy_url=normalized_url,
                masked_target=_mask_url_password(normalized_url),
                exists=True,
            )

        if scheme in ("postgres", "postgresql") or scheme.startswith("postgresql+"):
            if scheme == "postgres":
                normalized_url = f"postgresql+psycopg://{rest}"
            elif scheme == "postgresql":
                normalized_url = f"postgresql+psycopg://{rest}"
            else:
                normalized_url = target
            return ResolvedTarget(
                original_target=raw,
                resolved_from_env=resolved_from_env,
                dialect="postgresql",
                sqlalchemy_url=normalized_url,
                masked_target=_mask_url_password(normalized_url),
                exists=True,
            )

        if scheme in ("mysql", "mariadb") or scheme.startswith("mysql+") or scheme.startswith("mariadb+"):
            if scheme in ("mysql", "mariadb"):
                normalized_url = f"mysql+pymysql://{rest}"
            else:
                normalized_url = target
            return ResolvedTarget(
                original_target=raw,
                resolved_from_env=resolved_from_env,
                dialect="mysql",
                sqlalchemy_url=normalized_url,
                masked_target=_mask_url_password(normalized_url),
                exists=True,
            )

        return ResolvedTarget(
            original_target=raw,
            resolved_from_env=resolved_from_env,
            dialect=scheme.split("+")[0],
            sqlalchemy_url=target,
            masked_target=_mask_url_password(target),
            exists=True,
        )

    # 4. Otherwise treat as local SQLite file path
    return _validate_sqlite_file(Path(target), raw, resolved_from_env)
