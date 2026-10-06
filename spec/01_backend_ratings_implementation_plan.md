# Plan de Implementación Backend — Sistema de Ratings

**Alcance**: solo Backend (FastAPI + PostgreSQL + SQLAlchemy). Parte de `spec/00_course_ratings_system.md` y fue verificado contra el código por el agente `backend`.
**Estado de partida**: el sistema de ratings ya existe (modelo, migración `0e3a8766f785`, 6 endpoints, schemas, tests). Este plan cierra los defectos B1–B6.
**Regla**: todo comando va por Docker/Makefile desde `Backend/`. Antes de empezar: `docker-compose ps` y, si no están arriba, `make start`.

## Verificación de hallazgos

| # | Estado | Evidencia |
|---|---|---|
| B1 | Confirmado | La migración define `UNIQUE(course_id, user_id, deleted_at)`, que no impide duplicados activos porque `NULL ≠ NULL`. `CourseRating` no tiene `__table_args__` (su docstring dice "enforced by UNIQUE constraint", lo cual es falso). `add_course_rating` hace SELECT y luego INSERT sin lock ni manejo de `IntegrityError`. |
| B2 | Confirmado | `main.py:337-340` lanza `HTTPException(204)`. Además, `response_model=RatingResponse \| None` más un retorno `None` no produce un 204 válido. |
| B3 | Confirmado | `get_all_courses` (`course_service.py:28-52`) llama a `get_course_rating_stats` por curso (3 queries cada vez). |
| B4 | Confirmado | `specs/00_contracts.md` no documenta ratings ni `average_rating` / `total_ratings` / `rating_distribution`. |
| B5 | Confirmado, con matiz | `test_rating_endpoints.py:198-207` prueba el 204, pero con el servicio mockeado, así que no detecta el 204 inválido. |
| B6 | Confirmado | Sin autenticación. |

## Discrepancias spec vs código

1. `test_rating_db_constraints.py:68` tiene `test_unique_constraint_prevents_duplicate_active_ratings` con `@pytest.mark.skip`. Hay que quitarlo en la Fase 1. El test vecino `test_unique_constraint_allows_soft_deleted_duplicates` debe seguir pasando.
2. Los tests de constraints usan `SessionLocal` real, o sea la DB de desarrollo. No hay DB de test separada, así que hay que limpiar los datos que creen.
3. El docstring del `POST` en `main.py` dice "201 para nuevos", pero el endpoint devuelve 201 también al actualizar.
4. `get_all_courses` solo usa `average_rating` y `total_ratings`, no la distribución.
5. `rating_distribution` usa claves int, que JSON serializa como strings. Hay que documentarlo en el contrato.
6. No existen tests de `get_all_courses` con SQL real. Los actuales usan mocks.

## Orden y dependencias

`B1 → B2 → B3 → B4 → B5`. Los tests de cada fase se escriben junto con su cambio. La Fase 5 va al final para documentar el comportamiento real. Cada fase se valida por separado.

---

## Fase 1 — Unicidad real (B1, prioridad alta) — ✅ Completada

**Objetivo**: garantizar a nivel DB un solo rating activo por `(course_id, user_id)` y manejar la race condition en el servicio.

**Pasos**
- [x] 1. `app/models/course_rating.py`: declarar el índice único parcial sobre `(course_id, user_id)` con condición `deleted_at IS NULL`, y corregir el docstring.
- [x] 2. Crear la migración con `make create-migration`. Revisar el autogenerate a mano, porque Alembic no siempre detecta bien los índices parciales. `down_revision = '0e3a8766f785'`.
   - [x] `upgrade()`: primero resolver duplicados activos. Se conserva el más reciente por `(course_id, user_id)` y los demás reciben soft delete. Después se crea el índice parcial.
   - [x] Eliminar en la misma migración la constraint `uq_course_ratings_user_course_deleted`, que no sirve.
   - [x] `downgrade()`: restaurar la constraint vieja y eliminar el índice. Los duplicados con soft delete no se reconstruyen (documentarlo en el docstring).
- [x] 3. `CourseService.add_course_rating`: capturar `IntegrityError` en el INSERT, hacer `rollback()`, releer el rating activo y actualizarlo (upsert idempotente).
- [x] 4. Tests en `app/tests/test_rating_db_constraints.py`:
   - [x] Quitar el `skip`. El segundo insert activo debe lanzar `IntegrityError`.
   - [x] Tras un soft delete se permite un rating nuevo.
   - [x] Conviven dos soft-deleted y un activo.
   - [x] Test de servicio con DB real: dos `add_course_rating` seguidos del mismo usuario dejan una sola fila activa.

**Verificación**
- [x] `make migrate` y luego `alembic current` dentro del contenedor.
- [x] `pytest app/tests/test_rating_db_constraints.py -v` dentro del contenedor.
- [x] Probar `alembic downgrade -1` seguido de `alembic upgrade head`.
- [x] Opcional: sembrar duplicados activos con `psql` en el contenedor `db` antes de migrar.

**Aceptación** (cumplida): `\d course_ratings` muestra el índice parcial. El test de duplicado activo pasa sin skip. Upgrade, downgrade y upgrade funcionan. Con duplicados previos, la migración no falla y deja uno activo por par.

**Riesgos**
- El autogenerate puede omitir o malinterpretar la condición parcial.
- La limpieza de duplicados descarta ratings antiguos (recuperables por ser soft delete) y cambia promedios.
- El downgrade no puede reconstruir los duplicados.
- Los tests corren sobre la DB de desarrollo.
- Tras un `IntegrityError` hay que hacer `rollback()` correcto para no dejar la sesión inválida.

**Dependencias**: ninguna. Es prerrequisito del test de concurrencia de la Fase 4.

---

## Fase 2 — 204 válido (B2) — ✅ Completada

**Objetivo**: que `GET /courses/{course_id}/ratings/user/{user_id}` responda un 204 real, sin body, cuando no hay rating.

**Pasos**
- [x] 1. En `app/main.py` (~294-342): cuando no hay rating, devolver `Response(status_code=204)` en lugar de lanzar `HTTPException`. Ajustar `response_model` y la anotación de retorno para que FastAPI no intente validar el `Response`. Mantener `responses={200, 204}` para Swagger.
- [x] 2. Tests en `app/tests/test_rating_endpoints.py`:
   - [x] Endurecer `test_get_user_rating_not_exists`: status 204 y `response.content == b""`.
   - [x] Añadir un test contra el app real, sin mock del servicio, para confirmar que no hay error de protocolo.
- [x] 3. Decisión de contrato: se mantiene el 204 (no se pasa a 404), porque el cliente web lo tratará como `null`.
- [ ] 4. Avisar al agente `frontend` (F1) de que la ruta correcta es `/ratings/user/{user_id}` y que el 204 no trae body.

**Verificación**
- [x] `pytest app/tests/test_rating_endpoints.py -v` dentro del contenedor.
- [x] `curl -i http://localhost:8000/courses/1/ratings/user/99999`: 204, sin body.

**Aceptación** (cumplida): 204 sin body y sin warnings en `make logs`. El caso 200 con rating no cambia.

**Riesgos**: si queda `response_model` activo con la anotación anterior, FastAPI puede fallar al serializar el `Response`. El cambio es observable pero compatible, porque el cliente hoy no usa bien este endpoint (ruta errónea).

**Dependencias**: ninguna. Es independiente de la Fase 1.

---

## Fase 3 — Eliminar el N+1 en `get_all_courses` (B3)

**Objetivo**: el listado hace una sola query agregada con el mismo JSON de salida.

**Pasos**
1. Reemplazar el bucle por una sola query: `Course` con `LEFT JOIN` a `CourseRating` y `GROUP BY` curso.
   - El filtro `deleted_at IS NULL` de ratings va en la condición del JOIN, no en el WHERE, para no perder los cursos sin ratings.
   - Filtrar también `Course.deleted_at IS NULL`.
   - Castear el promedio a `float` (viene como `Decimal`), redondear a 2 decimales y devolver `0.0` / `0` si no hay ratings.
   - Fijar un orden estable.
   - Eliminar el `try/except ValueError`, que deja de ser necesario.
2. No tocar `get_course_by_slug`. Es un solo curso y las 3 queries de stats son aceptables.
3. Tests con DB real: un curso sin ratings, uno con ratings y uno con un rating soft-deleted. Contar queries con un listener `before_cursor_execute` y afirmar que es una (o como máximo dos). Mantener `test_main.py::test_get_all_courses_success`.

**Verificación**
- `pytest app -v` dentro del contenedor.
- Guardar el JSON de `/courses` antes del cambio y comparar con el posterior.

**Aceptación**: salida idéntica (campos, tipos y valores) para el seed. Una query por request. Los cursos sin ratings siguen apareciendo con `0.0` y `0`.

**Riesgos**: perder cursos sin ratings si el filtro va en el WHERE. Un cambio de tipo o valor rompería los tres clientes.

**Dependencias**: conviene hacerla después de la Fase 1 para probar sobre datos consistentes.

---

## Fase 4 — Tests faltantes (B5)

**Objetivo**: cubrir concurrencia, el 204 real y la no regresión del listado.

**Pasos**
1. Test de concurrencia (en `test_rating_db_constraints.py` o en un archivo nuevo): dos sesiones, una `SessionLocal()` por hilo, llamando a `add_course_rating` para el mismo curso y usuario. Resultado esperado: una fila activa y ambas llamadas exitosas. Limpiar las filas al final.
2. Confirmar que el test del 204 (Fase 2) y los de `/courses` (Fase 3) están en la suite completa.
3. Revisar que no queden filas de prueba en la DB. Usar slugs únicos, como ya hacen los fixtures.

**Verificación**: `pytest app -v` completo en el contenedor. Repetir 2–3 veces el test de concurrencia para detectar flakiness.

**Aceptación**: suite verde y estable, sin tests `skip` relacionados con ratings.

**Riesgos**: las sesiones SQLAlchemy no son thread-safe (una por hilo). Posible flakiness. Datos residuales en la DB de desarrollo.

**Dependencias**: Fases 1, 2 y 3.

---

## Fase 5 — Contrato (B4, B6)

**Objetivo**: que `Backend/specs/00_contracts.md` refleje la API real. Solo documentación, en el estilo del archivo.

**Pasos**
1. Añadir `average_rating` y `total_ratings` a `GET /courses`, y `rating_distribution` (claves `"1"`..`"5"` como strings) a `GET /courses/:slug`. Indicar `teacher_id[]` y `classes[]` con `id`, `name`, `description`, `slug` (sin duración).
2. Documentar los 6 endpoints de ratings con request, response y códigos:
   - `POST`: upsert, 201 al crear y al actualizar; 400 si el rating está fuera de 1–5; 404 si el curso no existe; 422 por validación.
   - `GET` lista: 404 si el curso no existe.
   - `GET stats`.
   - `GET user/{user_id}`: 200 o 204 sin body.
   - `PUT`: 404 si no existe; 400 si el `user_id` del body difiere del path.
   - `DELETE`: soft delete, 204; 404 si no existe.
3. Notas explícitas:
   - No hay autenticación: el `user_id` lo envía el cliente y no es una identidad confiable (B6).
   - La unicidad se garantiza con un índice parcial.
   - `PUT`/`DELETE` usan `/ratings/{user_id}`, mientras `GET` usa `/ratings/user/{user_id}`.
4. Señalar la discrepancia ya existente: el contrato define `/courses/:slug/classes/:id` y el backend expone `/classes/{class_id}` (con `duration = 0`). Se documenta, pero no se cambia la ruta sin avisar a los tres clientes.
5. Corregir el docstring del `POST` en `main.py` ("201 también al actualizar").

**Verificación**: revisar a mano contra `http://localhost:8000/docs` y con `curl` a cada endpoint.

**Aceptación**: cada endpoint de `main.py` está en el contrato con sus códigos y ninguna afirmación contradice el código.

**Riesgos**: el 201 en el update puede tentar a "arreglarlo". No se cambia, porque rompería al cliente.

**Dependencias**: Fases 1–3 cerradas, para no documentar comportamiento que cambia.

---

## Decisiones a confirmar

1. Estrategia de upsert concurrente: `try/except IntegrityError` (recomendada, por simplicidad) vs `INSERT ... ON CONFLICT`.
2. Duplicados previos: conservar el más reciente y hacer soft delete del resto (recomendado).
3. Mantener el 204 en `ratings/user/{user_id}` (recomendado) vs pasarlo a 404.
4. Eliminar la constraint `uq_course_ratings_user_course_deleted` en la misma migración (recomendado).

## Fuera de alcance

Autenticación real, FK a usuarios, nombres de profesores y duración por clase en el detalle, apps móviles.

## Archivos clave

- `Backend/app/models/course_rating.py`
- `Backend/app/alembic/versions/` (migración nueva, `down_revision = '0e3a8766f785'`)
- `Backend/app/main.py` (endpoint ~294-342 y docstring del POST ~157-180)
- `Backend/app/services/course_service.py` (`get_all_courses`, `add_course_rating`)
- `Backend/app/tests/test_rating_db_constraints.py`, `Backend/app/tests/test_rating_endpoints.py`
- `Backend/specs/00_contracts.md`
