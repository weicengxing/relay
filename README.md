# Relay

Initial scaffold for the free Java AI proxy MVP.

## Layout

- `frontend/` - Vue 3 + Vite
- `backend/` - Spring Boot API
- `backend/src/main/resources/db/schema.sql` - baseline PostgreSQL schema

## Current stack

- Vue 3.5.34
- Vite 7.3.3
- @vitejs/plugin-vue 6.0.6
- Spring Boot 4.0.4

## Next steps

1. Add persistence wiring when Supabase credentials are ready.
2. Add authentication and request forwarding after the API contract is settled.
3. Connect the frontend shell to stable backend endpoints.

## Backend Commands

```powershell
cd D:\relay\backend
mvn test
mvn spring-boot:run
```
