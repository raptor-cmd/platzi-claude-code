# Platziflix - Memoria del Proyecto

Plataforma de cursos online (estilo Netflix). Monorepo con **un backend y tres clientes** (web, Android, iOS) que no comparten código: el único contrato entre ellos es el JSON de la API REST (ver `Backend/specs/00_contracts.md`).

## Reglas obligatorias

1. **Backend siempre vía Docker**: todo comando del Backend se ejecuta dentro del contenedor `api`. Antes de ejecutarlo, verifica que los contenedores estén arriba (`docker-compose ps`; si no, `make start`). Revisa `Backend/Makefile` y usa sus targets existentes en lugar de inventar comandos.
2. **La API REST es la única fuente de datos** para Frontend y Mobile. Un cambio en un endpoint o en su JSON impacta a los 3 clientes: revisa web, Android e iOS.
3. **Testing requerido** para toda funcionalidad nueva.
4. **Cambios de DB = migración Alembic** (nunca editar el esquema a mano).
5. **TypeScript strict** en Frontend.
6. **Naming**: snake_case (Python), camelCase (JS/TS), PascalCase (Swift/Kotlin y componentes React).

## Arquitectura

```
                 PostgreSQL 15 (Docker, :5432)
                          ▲  SQLAlchemy 2.0 / Alembic
                 FastAPI (Docker, :8000)
                 main.py → services/CourseService → models/
        ┌─────────────────┼──────────────────┐
   Next.js 15 :3000   Android (Kotlin)   iOS (Swift)
   localhost:8000     10.0.2.2:8000      localhost:8000
```

```
platzi-claude-code/
├── Backend/    # FastAPI + PostgreSQL (Docker), specs/ con contratos
├── Frontend/   # Next.js 15 (App Router)
└── Mobile/
    ├── PlatziFlixAndroid/   # Kotlin + Jetpack Compose
    └── PlatziFlixiOS/       # Swift + SwiftUI
```

## Backend (`Backend/`)

- **Stack**: FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL 15, UV, Docker Compose.
- **Capas**: `app/main.py` (rutas, `Depends(get_db)` / `Depends(get_course_service)`) → `app/services/course_service.py` (lógica de negocio, clase `CourseService`) → `app/models/` (SQLAlchemy). Schemas Pydantic en `app/schemas/` (hoy solo `rating.py`). Config en `app/core/config.py`, engine/sesión en `app/db/base.py`, seed en `app/db/seed.py`.
- **Modelos**: `Course`, `Teacher`, `Lesson`, `Class_` (`class_.py`), `CourseRating`, tabla puente `course_teachers`. Todos heredan de `BaseModel` (`created_at`, `updated_at`, `deleted_at`) y usan **soft delete**: filtrar siempre `deleted_at IS NULL`.
- **Relaciones**: Course ↔ Teacher (N:M), Course → Lesson (1:N), Course → CourseRating (1:N).
- **Migraciones**: `Backend/app/alembic/versions/` (inicial + `0e3a8766f785_add_course_ratings_table`).
- **Tests**: `app/tests/` (`test_course_rating_service.py`, `test_rating_db_constraints.py`, `test_rating_endpoints.py`) y `app/test_main.py`. Ver `app/TESTING_README.md`.

### Endpoints

| Método | Ruta | Notas |
|---|---|---|
| GET | `/` | Bienvenida |
| GET | `/health` | Estado + conectividad DB (`COUNT(*)` de `courses`) |
| GET | `/courses` | Lista con `average_rating` y `total_ratings` |
| GET | `/courses/{slug}` | Detalle: `teacher_id[]`, `classes[]`, rating + `rating_distribution` |
| GET | `/classes/{class_id}` | Lee de `Lesson`; devuelve `title`, `video`, `duration` (0, TODO) |
| POST | `/courses/{course_id}/ratings` | Crea o actualiza (upsert), 201 |
| GET | `/courses/{course_id}/ratings` | Ratings activos, más nuevos primero |
| GET | `/courses/{course_id}/ratings/stats` | Promedio, total, distribución 1-5 |
| GET | `/courses/{course_id}/ratings/user/{user_id}` | Rating de un usuario |
| PUT | `/courses/{course_id}/ratings/{user_id}` | Actualiza; 404 si no existe |
| DELETE | `/courses/{course_id}/ratings/{user_id}` | Soft delete, 204 |

### Sistema de ratings (reglas de negocio)
- Valor 1–5, validado en servicio **y** con `CheckConstraint` en DB.
- Un rating activo por usuario y curso.
- `user_id` lo envía el cliente: **no hay autenticación ni FK a usuarios**.
- Las estadísticas se agregan en SQL (`get_course_rating_stats`); preferirlas a las properties Python de `Course`.

### Comandos (ejecutar desde `Backend/`)
```bash
make start            # docker-compose up -d
make stop             # docker-compose down
make restart          # reiniciar contenedores
make build            # construir imágenes
make logs             # logs en vivo
make migrate          # alembic upgrade head (dentro del contenedor api)
make create-migration # alembic revision --autogenerate (pide mensaje)
make seed             # poblar datos
make seed-fresh       # limpiar y re-poblar
make clean            # ¡borra contenedores, volúmenes e imágenes!
```
Otros comandos (p. ej. pytest) se ejecutan dentro del contenedor: `docker-compose exec api bash -c "cd /app && uv run <comando>"`.

### Base de datos (Docker)
Usuario `platziflix_user`, password `platziflix_password`, DB `platziflix_db`, puerto 5432. `DATABASE_URL=postgresql://platziflix_user:platziflix_password@db:5432/platziflix_db`.

## Frontend (`Frontend/`)

- **Stack**: Next.js 15.3.3 (App Router, Turbopack en dev), React 19, TypeScript, SCSS + CSS Modules, Vitest + React Testing Library. Gestor: **yarn**.
- **Rutas** (`src/app/`): `/` catálogo en grid · `/course/[slug]` detalle (con `loading`, `error`, `not-found`) · `/classes/[class_id]` reproductor.
- **Componentes** (`src/components/`): `Course`, `CourseDetail`, `StarRating`, `VideoPlayer` (cada uno con su test y `.module.scss`).
- **Datos**: Server Components con `fetch(url, { cache: "no-store" })`. `src/services/ratingsApi.ts` es el cliente tipado de ratings (timeout, `ApiError`) y usa `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`). Tipos en `src/types/` (`index.ts`, `rating.ts`). Estilos globales en `src/styles/` (`reset.scss`, `vars.scss`).
- En Next 15, `params` es una `Promise` en páginas: hacer `await params`.

```bash
cd Frontend
yarn dev     # http://localhost:3000
yarn build
yarn test    # vitest
yarn lint
```

## Mobile (`Mobile/`)

Ambas apps siguen Clean Architecture: `data` (DTO → Mapper) · `domain` (modelos + contrato de repositorio) · `presentation` (ViewModel + UI). Cada una tiene `.cursor/context/` con contratos y prompts de referencia.

- **Android** (`PlatziFlixAndroid`, paquete `com.espaciotiago.platziflixandroid`): Kotlin, Jetpack Compose, MVVM (`CourseListViewModel` + `CourseListUiState`), Retrofit + OkHttp + Gson (`data/network/ApiService.kt`, `NetworkModule.kt`), DI manual en `di/AppModule.kt` con flag `USE_MOCK_DATA` (hoy `false`). Base URL `http://10.0.2.2:8000/` (emulador). Solo consume `GET /courses`.
- **iOS** (`PlatziFlixiOS`): Swift, SwiftUI, MVVM + Repository (`CourseRepositoryProtocol`, `RemoteCourseRepository`), Mappers, red en `Services/` (`NetworkManager`, `APIEndpoint`, `NetworkError`). Base URL `http://localhost:8000` en `Data/Repositories/CourseAPIEndpoints.swift`. Endpoints: `/courses` y `/courses/{slug}`.
- Ningún DTO móvil incluye aún `average_rating` / `total_ratings`.

## URLs

- Backend API: http://localhost:8000 · Swagger: http://localhost:8000/docs
- Frontend: http://localhost:3000

## Estado de funcionalidades

Implementado: catálogo, detalle de curso, navegación por slug, reproductor de video, health checks, sistema de ratings (backend + `StarRating` y `ratingsApi` en web), apps móviles con listado de cursos.

## Deuda técnica / problemas conocidos

Verificar si siguen vigentes antes de asumirlos:
1. `ratingsApi.getUserRating` llama a `/ratings/{userId}`, pero el backend expone `/ratings/user/{user_id}`.
2. El endpoint `GET .../ratings/user/{user_id}` lanza `HTTPException(204)` (no es una forma válida de responder 204 en FastAPI).
3. `generateMetadata` en `course/[slug]/page.tsx` usa `courseData.title`, pero la API devuelve `name`; además no hace `await` a `params`.
4. El botón "Regresar al curso" de `/classes/[class_id]` apunta a `/course` (ruta inexistente).
5. Contrato vs implementación: la spec define `/courses/:slug/classes/:id`, pero existe `/classes/{id}` leyendo de `Lesson`.
6. `get_all_courses` hace consultas de ratings por cada curso (N+1).
7. URLs del backend hardcodeadas en los tres clientes, sin configuración por entorno (en web, solo `ratingsApi` usa env var).
8. Móviles sin ratings; iOS no consume el detalle de curso en la UI.
9. Sin autenticación: `user_id` de ratings es confiado desde el cliente.

# Para tests

Cualquier comando que necesites ejecutar para el Backend debe ser dentro del contenedor de docker API, antes de ejecutarlo certifica que esté funcionando el contenedor y revisa el archivo makefile con los comandos que existen y úsalos