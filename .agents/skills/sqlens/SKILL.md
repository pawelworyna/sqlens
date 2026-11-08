---
name: sqlens
description: Bezpieczna inspekcja tylko do odczytu (read-only) baz danych SQLite, SQL Server (MSSQL), PostgreSQL oraz MySQL za pomocą serwera MCP sqlens. Używaj zawsze, gdy użytkownik podaje ścieżkę do pliku bazy danych, URI połączenia, connection string lub nazwę profilu bazy i prosi o sprawdzenie danych lub struktury.
---

# SQLens — Procedura Inspekcji Baz Danych (SQLite, SQL Server, PostgreSQL, MySQL)

Kiedy użytkownik podaje w prompcie ścieżkę do bazy danych (np. plik `.db` / `.sqlite`), connection string, URI lub nazwę profilu z `.env` oraz opisuje, co chce sprawdzić, **MUSISZ** bezwzględnie przestrzegać poniższej 3-etapowej procedury.

## Krok 1: Weryfikacja istnienia bazy i pobranie schematu (OBOWIĄZKOWY)
1. **Zawsze jako pierwsze** wywołaj narzędzie `inspect_database(connection_target=...)`.
2. **Zakaz zgadywania**: Nigdy nie wywołuj `execute_query` w ciemno i nie zgaduj nazw tabel ani kolumn przed wywołaniem `inspect_database`.
3. Sprawdź pole `exists` w odpowiedzi:
   - Jeśli `exists: false` — **natychmiast przerwij** dalsze kroki i poinformuj użytkownika o błędzie (np. że plik bazy pod podaną ścieżką nie istnieje lub serwer SQL jest niedostępny). Nie próbuj wykonywać żadnych zapytań SQL.
   - Jeśli `exists: true` — zapoznaj się z polem `dialect` (`sqlite`, `mssql`, `postgresql`, `mysql`) oraz listą `tables` i `views` (nazwy tabel, schematy, nazwy kolumn, typy danych, klucze główne `primary_keys` i klucze obce `foreign_keys`).

## Krok 2: Przetworzenie intencji użytkownika na zapytanie SQL
Na podstawie poznanego w Kroku 1 schematu oraz dialektu bazy (`dialect`), przetłumacz zamiar użytkownika na pojedyncze zapytanie tylko do odczytu (`SELECT` lub `WITH ... SELECT`):
- **Dla SQL Server (`dialect == "mssql"`)**:
  - Używaj `SELECT TOP N ...` zamiast `LIMIT N` (lub `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY` przy `ORDER BY`).
  - Uwzględniaj nazwę schematu (np. `dbo.TableName` lub `[dbo].[TableName]`).
  - Używaj nawiasów kwadratowych `[NazwaKolumny]` dla identyfikatorów ze spacjami lub słów kluczowych.
- **Dla SQLite (`dialect == "sqlite"`), PostgreSQL (`dialect == "postgresql"`), MySQL (`dialect == "mysql"`)**:
  - Używaj klauzuli `LIMIT N` na końcu zapytania.
- Używaj wyłącznie rzeczywistych nazw tabel i kolumn zwróconych przez `inspect_database`.
- Nigdy nie generuj zapytań modyfikujących dane (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `CREATE`, `EXEC`, `SELECT ... INTO`).

## Krok 3: Wykonanie zapytania i prezentacja wyniku
1. Wywołaj narzędzie `execute_query(connection_target=..., sql_query=..., max_rows=...)`.
2. Jeśli zapytanie zwróci błąd składniowy, przeanalizuj komunikat błędu w kontekście schematu z Kroku 1, popraw zapytanie i wywołaj `execute_query` ponownie.
3. Przedstaw użytkownikowi czytelne podsumowanie wyników (np. w tabeli Markdown) oraz pokaż dokładne zapytanie SQL, które zostało wykonane.
