# SQLens — Multi-DB Read-Only Inspection MCP Server

**SQLens** to serwer MCP (Model Context Protocol) w Pythonie służący do bezpiecznej inspekcji baz danych **SQLite**, **SQL Server (MSSQL)** oraz opcjonalnie **PostgreSQL** i **MySQL** w trybie tylko do odczytu (`read-only`).

Wymusza na modelu LLM bezpieczny 3-krokowy przepływ pracy:
1. **`inspect_database`**: Sprawdzenie, czy plik bazy danych istnieje (lub czy serwer SQL jest osiągalny), rozpoznanie dialektu (`sqlite`, `mssql`, `postgresql`, `mysql`) oraz pobranie pełnego schematu (tabele, widoki, kolumny, typy danych, klucze główne i obce).
2. **Konstrukcja zapytania SQL przez LLM**: Przetłumaczenie intencji użytkownika z promptu na zapytanie `SELECT` dopasowane do rzeczywistego schematu i dialektu (np. `SELECT TOP N` w T-SQL vs `LIMIT N` w SQLite/Postgres/MySQL).
3. **`execute_query`**: Wykonanie zapytania w trybie tylko do odczytu z walidacją bezpieczeństwa i zwrócenie wierszy wyniku.

---

## Instalacja

Sklonuj repozytorium i zainstaluj zależności w wirtualnym środowisku `.venv`:

```powershell
git clone https://github.com/<twoj-login>/sqlens.git
cd sqlens

# Utworzenie środowiska wirtualnego
python -m venv .venv

# Instalacja SQLens (obsługa SQLite + SQL Server + testy)
.\.venv\Scripts\pip install -e ".[dev]"

# OPCJONALNIE: Instalacja ze sterownikami PostgreSQL i MySQL
.\.venv\Scripts\pip install -e ".[all,dev]"
```

*(Opcjonalnie)* Jeśli łączysz się z **SQL Server**, **PostgreSQL** lub **MySQL**, możesz zapisać profile połączeń w pliku `.env` w głównym katalogu repozytorium (wzór znajdziesz w [`.env.example`](.env.example)), aby nie podawać haseł w prompcie:

```env
MSSQL_LOCAL="Driver={ODBC Driver 18 for SQL Server};Server=localhost;Database=MojaBaza;Trusted_Connection=yes;TrustServerCertificate=yes;"
MSSQL_PROD="mssql+pymssql://uzytkownik:haslo@10.0.0.5:1433/ERP"
```

---

## Jak użyć SQLens w poszczególnych środowiskach

> **Uwaga**: W poniższych konfiguracjach zamień `C:/path/to/sqlens` na rzeczywistą ścieżkę do sklonowanego repozytorium na Twoim dysku.

### 1. GitHub Copilot w VS Code

#### A. Użycie lokalne (w tym repozytorium)
Plik [`.vscode/mcp.json`](.vscode/mcp.json) oraz instrukcje [`.github/copilot-instructions.md`](.github/copilot-instructions.md) są już skonfigurowane w projekcie.
1. Otwórz folder repozytorium w VS Code.
2. Otwórz **GitHub Copilot Chat** (`Ctrl+Alt+I`) i przełącz tryb na **Agent Mode**.
3. Kliknij ikonę narzędzi (🔧) w polu czatu — zobaczysz aktywny serwer **`sqlens`** z narzędziami `inspect_database` oraz `execute_query`.

#### B. Użycie globalne (w dowolnym projekcie w VS Code)
Aby korzystać z `sqlens` w każdym otwartym projekcie:
1. W VS Code naciśnij `Ctrl+Shift+P` -> wybierz **MCP: Open User Configuration** (lub otwórz swój plik `settings.json`).
2. Dodaj konfigurację:
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

**GitHub Copilot Coding Agent CLI** obsługuje serwery MCP oraz automatycznie wczytuje pliki [`AGENTS.md`](AGENTS.md) i [`.github/copilot-instructions.md`](.github/copilot-instructions.md).

1. Dodaj serwer do globalnej konfiguracji MCP dla Copilot CLI (`~/.copilot/mcp-config.json`):
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
2. Możesz też dodać serwer interaktywnie z poziomu CLI:
   - Uruchom `copilot`, wpisz komendę `/mcp add` i podaj:
     - **Name**: `sqlens`
     - **Command**: `C:/path/to/sqlens/.venv/Scripts/python.exe -m sqlens`

---

### 3. Antigravity

Projekt posiada gotowy Skill w [`.agents/skills/sqlens/SKILL.md`](.agents/skills/sqlens/SKILL.md) oraz reguły w [`AGENTS.md`](AGENTS.md).

1. Dodaj serwer `sqlens` do pliku konfiguracji MCP Antigravity (`~/.gemini/antigravity/mcp_config.json`):
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
2. *(Opcjonalnie — Skill globalny)* Aby Antigravity pamiętał procedurę `SKILL.md` także wtedy, gdy pracujesz w innym repozytorium, skopiuj folder `.agents/skills/sqlens` do globalnego katalogu skilli Antigravity:
```powershell
Copy-Item -Recurse -Force ".\.agents\skills\sqlens" "$HOME\.gemini\antigravity\skills\sqlens"
```

---

### 4. OpenAI Codex CLI (`codex`)

Codex CLI natywnie wspiera serwery MCP w pliku `~/.codex/config.toml` oraz automatycznie czyta instrukcje z [`AGENTS.md`](AGENTS.md) (a także z globalnego `~/.codex/AGENTS.md`).

1. Otwórz (lub utwórz) plik `~/.codex/config.toml` i dodaj sekcję:
```toml
[mcp_servers.sqlens]
command = 'C:/path/to/sqlens/.venv/Scripts/python.exe'
args = ["-m", "sqlens"]
env = { "PYTHONUTF8" = "1" }
startup_timeout_sec = 15
tool_timeout_sec = 60
```
2. *(Alternatywnie z linii komend)* Możesz zarejestrować serwer poleceniem:
```powershell
codex mcp add sqlens -- C:/path/to/sqlens/.venv/Scripts/python.exe -m sqlens
```
3. *(Opcjonalnie — instrukcje globalne)* Aby Codex w każdym katalogu pamiętał o kolejności `inspect_database` -> `execute_query`, możesz dopisać zawartość pliku [`AGENTS.md`](AGENTS.md) do `~/.codex/AGENTS.md`.

---

### 5. Hermes (`hermes-agent`)

Hermes obsługuje serwery MCP przez `stdio` oraz natywnie wspiera system skilli `SKILL.md`.

1. Otwórz plik konfiguracyjny Hermesa (`~/.hermes/config.yaml`) i dodaj wpis w sekcji `mcp_servers`:
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
2. Skopiuj skill [`.agents/skills/sqlens/SKILL.md`](.agents/skills/sqlens/SKILL.md) do katalogu skilli Hermesa (`~/.hermes/skills/sqlens/SKILL.md`), aby Hermes zawsze stosował 3-etapową procedurę:
```powershell
New-Item -ItemType Directory -Force -Path "$HOME\.hermes\skills\sqlens"
Copy-Item -Force ".\.agents\skills\sqlens\SKILL.md" "$HOME\.hermes\skills\sqlens\SKILL.md"
```

---

## Przykłady użycia w prompcie (identyczne w każdym środowisku)

Niezależnie od tego, czy piszesz w **GitHub Copilot**, **Antigravity**, **Codex** czy **Hermes**, po prostu podajesz namiar na bazę i piszesz co chcesz sprawdzić:

- **SQLite (ścieżka do pliku)**:
  > *"Sprawdź w bazie `C:/dane/sklep.db` jakie są tabele i pokaż 5 klientów z największą sumą zamówień."*

- **SQL Server (przez nazwę profilu z `.env`)**:
  > *"W bazie `MSSQL_LOCAL` sprawdź strukturę tabel związanych z fakturami i wypisz 10 ostatnich nieopłaconych faktur."*

- **SQL Server (przez bezpośredni connection string / URI)**:
  > *"Sprawdź w bazie `mssql+pymssql://sa:Haslo123@localhost:1433/Magazyn` stany magazynowe produktów, których ilość spadła poniżej 5 sztuk."*

- **PostgreSQL / MySQL**:
  > *"Sprawdź w `postgresql://postgres:secret@localhost:5432/analytics` ilu nowych użytkowników zarejestrowało się w ostatnim miesiącu."*

Co zrobi agent pod spodem:
1. Najpierw wywoła `inspect_database(connection_target=...)` — sprawdzi czy baza istnieje, odczyta dialekt (`sqlite` / `mssql` / `postgresql` / `mysql`) i pobierze wszystkie tabele, kolumny oraz klucze obce.
2. Następnie sam ułoży zapytanie `SELECT` dopasowane do schematu i dialektu (np. `SELECT TOP 10` dla SQL Servera lub `LIMIT 5` dla SQLite).
3. Na końcu wywoła `execute_query(connection_target=..., sql_query=...)` i zaprezentuje wynik.

---

## Uruchamianie testów

```powershell
.\.venv\Scripts\pytest -v
```

## Licencja

[MIT](LICENSE)
