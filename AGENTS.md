# Instrukcje dla Agentów AI (Codex, GitHub Copilot, Antigravity, Hermes)

W tym środowisku dostępny jest serwer MCP **`sqlens`** służący do bezpiecznej inspekcji (tylko do odczytu) baz danych **SQLite**, **SQL Server (MSSQL)**, **PostgreSQL** oraz **MySQL**.

## Obowiązkowy przepływ pracy z bazami danych (`sqlens`)

Gdy użytkownik podaje ścieżkę do pliku bazy (np. `C:/.../baza.db`), connection string, URI lub nazwę profilu z `.env` i opisuje co chce sprawdzić:

1. **KROK 1 — Sprawdzenie istnienia bazy i pobranie schematu (`inspect_database`)**:
   - **ZAWSZE** rozpocznij od wywołania `inspect_database(connection_target=...)`.
   - Nigdy nie uruchamiaj `execute_query` przed wcześniejszym pobraniem schematu przez `inspect_database`.
   - Jeśli `inspect_database` zwróci `"exists": false`, zatrzymaj się i poinformuj użytkownika, że baza nie istnieje lub jest niedostępna.

2. **KROK 2 — Konstrukcja zapytania SQL dopasowanego do dialektu**:
   - Sprawdź pole `"dialect"` zwrócone przez `inspect_database`:
     - **`mssql` (SQL Server)**: używaj składni T-SQL (`SELECT TOP N ...`, `[schema].[table]`, np. `dbo.Users`). Nie używaj `LIMIT`.
     - **`sqlite` / `postgresql` / `mysql`**: używaj `LIMIT N`.
   - Korzystaj wyłącznie z dokładnych nazw tabel, widoków, kolumn oraz relacji kluczy obcych odczytanych z `inspect_database`.
   - Dozwolone są wyłącznie zapytania tylko do odczytu (`SELECT`, `WITH`, `EXPLAIN`, `PRAGMA`, `SHOW`).

3. **KROK 3 — Wykonanie zapytania (`execute_query`)**:
   - Wywołaj `execute_query(connection_target=..., sql_query=...)`.
   - Zaprezentuj wyniki w czytelnej formie i podaj wykonane zapytanie SQL.
