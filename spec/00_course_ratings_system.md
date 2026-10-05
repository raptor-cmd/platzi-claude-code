# Análisis Técnico: Sistema de Ratings de Cursos (1–5 estrellas)

> Alcance: **Backend y Frontend**. Las apps móviles (Android/iOS) quedan fuera de este spec.

## Estado actual

Verificado leyendo el código (no solo CLAUDE.md):

- **Backend: completo.**
  - Modelo `CourseRating` (`app/models/course_rating.py`) con `CheckConstraint` 1–5 y soft delete.
  - Migración `0e3a8766f785_add_course_ratings_table`.
  - 6 endpoints de ratings en `app/main.py`.
  - Estadísticas agregadas en SQL (`CourseService.get_course_rating_stats`).
  - Schemas Pydantic en `app/schemas/rating.py`.
  - Tests en `app/tests/` (servicio, constraints de DB, endpoints).
  - `GET /courses` ya devuelve `average_rating` y `total_ratings`; `GET /courses/{slug}` además devuelve `rating_distribution`.
- **Frontend: parcial.**
  - `StarRating` es solo lectura y se usa en el catálogo (`Course.tsx`).
  - `ratingsApi.ts` y los tipos (`types/rating.ts`) existen, pero **ningún componente los usa**.
  - El detalle del curso no muestra ratings.

## Problema

Falta cerrar el feature: los usuarios deben poder **ver** el resumen de ratings de un curso y **calificar, editar y borrar** su rating desde la web. Antes hay defectos en el backend y en el cliente que lo impiden o lo hacen incorrecto.

## Impacto Arquitectural

### Backend

| # | Hallazgo | Ubicación |
|---|---|---|
| B1 | **Unicidad no garantizada.** `UNIQUE(course_id, user_id, deleted_at)` no impide dos ratings activos del mismo usuario porque en PostgreSQL `NULL ≠ NULL`. Dos POST concurrentes pueden duplicar y distorsionar el promedio. | migración `0e3a8766f785`, `course_rating.py` |
| B2 | `GET /courses/{id}/ratings/user/{user_id}` lanza `HTTPException(204)`, forma no válida en FastAPI. | `main.py:337` |
| B3 | N+1 en `get_all_courses`: por curso hace ~3 queries (existencia, avg/count, distribución). | `course_service.py:28-52` |
| B4 | `specs/00_contracts.md` no documenta ratings. `POST` devuelve 201 también al actualizar (upsert) y no está dicho. | `Backend/specs/00_contracts.md` |
| B5 | Faltan tests de concurrencia (B1) y del 204 (B2). | `app/tests/` |
| B6 | Sin autenticación: el `user_id` lo envía el cliente y se confía en él. | global |

### Frontend

| # | Hallazgo | Ubicación |
|---|---|---|
| F1 | `getUserRating` llama a `/ratings/{userId}`; el backend expone `/ratings/user/{userId}`. Además `handleApiResponse` falla si la respuesta no trae `content-type` JSON (caso 204). | `services/ratingsApi.ts:139-161` |
| F2 | `RatingStats` no incluye `rating_distribution`; `CourseDetail` no declara los campos de rating con la forma real de la API. | `types/rating.ts`, `types/index.ts` |
| F3 | `CourseDetail` ya está desalineado con la API (independiente de ratings): usa `course.title`/`course.teacher`, la API devuelve `name`/`teacher_id[]`; usa `cls.title`/`cls.duration`, el detalle devuelve `name` y no devuelve duración. Lo mismo en `generateMetadata` (`course/[slug]/page.tsx`), que además no hace `await params`. | `CourseDetail.tsx`, `course/[slug]/page.tsx` |
| F4 | No existe componente interactivo para calificar (`StarRating` ignora la prop `readonly`). | `components/StarRating` |
| F5 | `<linearGradient id="halfStarGradient">` se repite en cada estrella → IDs duplicados en el DOM. | `StarRating.tsx:34` |
| F6 | Sin origen para `user_id`. | — |
| F7 | Faltan tests: input interactivo, `ratingsApi`, detalle. | `components/**/__tests__` |

### Base de datos

- Nueva migración Alembic: índice único parcial `UNIQUE (course_id, user_id) WHERE deleted_at IS NULL` (B1). Debe limpiar o detectar duplicados activos antes de crearlo.

### Contrato API

- Todos los cambios son **compatibles hacia atrás**: no se quitan ni renombran campos de `/courses` ni `/courses/{slug}`.
- Único cambio de comportamiento observable: `ratings/user/{user_id}` pasa a responder un 204 válido (B2).
- Una futura autenticación cambiaría el contrato de ratings (el `user_id` saldría del token y dejaría de ir en el body).

## Riesgos

- **Concurrencia (B1):** sin el índice parcial, el promedio puede quedar corrupto. Prioridad alta.
- **Seguridad (B6):** cualquiera puede calificar como cualquier `user_id`. Aceptable para un MVP; debe quedar documentado.
- **Datos existentes:** la migración de B1 puede fallar si ya hay duplicados activos; resolverlo dentro de la migración.
- **Desalineación del detalle (F3):** si no se arregla primero, la UI de ratings se monta sobre una página que ya muestra datos incorrectos.
- **`user_id` en `localStorage` (F6):** es provisional y manipulable.

## Decisiones tomadas / pendientes

- **Pendiente:** identidad del usuario (¿`user_id` en `localStorage` por ahora, o auth primero?). El plan asume `localStorage` provisional.
- **Pendiente:** ¿el arreglo del detalle web (F3) entra en este spec? El plan lo incluye como Fase 2 por ser prerrequisito de la UI.

## Propuesta de Solución

Respetar las capas existentes: `main.py` → `CourseService` → `models`. Sin capa Repository nueva.

- **Backend:** migración con índice parcial; 204 correcto; listado con una sola query agregada; contrato documentado; tests.
- **Frontend:** cliente `ratingsApi` corregido y tipado; `CourseDetail` alineado a la API; componente cliente `RatingInput` (accesible, `radiogroup`) y un bloque de resumen con distribución; el refresco usa `router.refresh()` dado que los datos se piden con `cache: "no-store"`.

## Plan de Implementación

Cada fase es verificable por separado y permite validación humana entre pasos.

### Fase 1 — Backend (agente `backend`)
Comandos siempre vía Docker (`make migrate`; pytest con `docker-compose exec api bash -c "cd /app && uv run pytest ..."`).

1. **B1:** crear migración (`make create-migration`) con el índice único parcial y manejo de duplicados previos; actualizar `CourseRating.__table_args__`. Ejecutar `make migrate`.
2. **B2:** `get_user_course_rating` devuelve `Response(status_code=204)` cuando no hay rating.
3. **B3:** reemplazar el bucle N+1 de `get_all_courses` por una agregación `GROUP BY course_id` con `LEFT JOIN`, filtrando `deleted_at IS NULL` en ambas tablas.
4. **B5:** tests: unicidad con índice parcial (segundo insert activo falla, tras soft delete se permite), 204 correcto, y que `/courses` conserve `average_rating`/`total_ratings` (sin regresión).
5. **B4:** documentar ratings en `Backend/specs/00_contracts.md` (endpoints, códigos, upsert con 201).

### Fase 2 — Frontend: cliente y contrato (agente `frontend`)
6. **F1:** corregir la ruta de `getUserRating` y tratar el 204 como `null` en `ratingsApi.ts`.
7. **F2:** añadir `rating_distribution` a los tipos; tipar `CourseDetail` según la API real.
8. **F3:** alinear `CourseDetail.tsx` y `generateMetadata` con `name`, `teacher_id[]` y `classes[].name`; hacer `await params`; manejar la duración ausente.
9. **F5:** hacer único el id del gradiente de `StarRating`.

### Fase 3 — Frontend: UI de ratings (agente `frontend`)
10. **F6:** hook/utilidad que genere y persista un `user_id` en `localStorage` (con manejo de fallo de acceso).
11. **F4:** `RatingInput` (`"use client"`): hover, click, teclado, `role="radiogroup"`, estados de carga y error, actualización optimista.
12. Bloque de resumen en `CourseDetail`: promedio, total, barras de distribución y rating propio con editar/borrar; `router.refresh()` tras cada cambio.
13. **F7:** tests Vitest/RTL de `RatingInput`, `ratingsApi` (fetch mockeado) y del bloque de resumen.

### Verificación final
14. `yarn lint`, `yarn test`, `yarn build` en `Frontend/`; pytest completo en el contenedor `api`.
15. Prueba manual: calificar, editar, borrar y comprobar que catálogo y detalle muestran el mismo promedio.

## Fuera de alcance

- Apps móviles (Android/iOS).
- Autenticación real y FK a una tabla de usuarios.
- Reseñas con texto, moderación y ordenamiento por rating.
