# Revisión de Seguridad — Backend Ratings, Fases 3, 4 y 5

**Alcance**: cambios sin commitear en `master` tras implementar las Fases 3, 4 y 5 de `spec/01_backend_ratings_implementation_plan.md`.
**Método**: `/security-review` con umbral de confianza ≥ 8/10 y reglas de falsos positivos. El diff llegó vacío a la revisión, así que el análisis se hizo leyendo el código y el `git status`.
**Resultado**: **0 hallazgos de alta confianza.**
**Relación con otros docs**: `spec/03_backend_security_review.md` documenta la ausencia de autenticación en los endpoints de ratings. Aquí no se repite, porque ya existía antes de estos cambios (ver "Deuda de seguridad preexistente").

## Archivos revisados

| Archivo | Cambio | Relevancia de seguridad |
|---|---|---|
| `Backend/app/services/course_service.py` | `get_all_courses` pasa de N+1 a una sola query (`LEFT JOIN` + `GROUP BY`) | Revisado. Sin hallazgos |
| `Backend/app/main.py` | Solo el docstring del POST de ratings | Sin impacto |
| `Backend/app/tests/test_rating_db_constraints.py` | Test de concurrencia con hilos | Excluido (solo tests) |
| `Backend/app/tests/test_get_all_courses_query.py` | Tests nuevos de `get_all_courses` | Excluido (solo tests) |
| `Backend/specs/00_contracts.md` | Contrato de `/courses` y ratings | Excluido (documentación) |
| `spec/01_backend_ratings_implementation_plan.md` | Fases marcadas como completadas | Excluido (documentación) |
| `CLAUDE.md` | Regla Docker para tests | Excluido (documentación) |

## Análisis de `get_all_courses`

| Aspecto | Conclusión |
|---|---|
| Inyección SQL | La query usa expresiones del ORM (`func.avg`, `func.count`, `outerjoin`, `filter`). El método no recibe parámetros, así que no hay entrada de usuario en el SQL. |
| Filtro de soft delete | Se mantiene `Course.deleted_at IS NULL`. El filtro de ratings activos (`CourseRating.deleted_at IS NULL`) va en la condición del `JOIN`, no en el `WHERE`. Un curso eliminado no aparece y un rating eliminado no cuenta. |
| Exposición de datos | Los campos devueltos son los mismos que antes: `id`, `name`, `description`, `thumbnail`, `slug`, `average_rating`, `total_ratings`. El JSON de `/courses` es idéntico al anterior (se comparó antes y después). |
| Manejo de errores | Se eliminó un `try/except ValueError` que ya no tenía sentido. No hay errores nuevos que filtren detalles internos. |

## Deuda de seguridad preexistente (no atribuible a este cambio)

| Tema | Estado | Referencia |
|---|---|---|
| El `user_id` lo envía el cliente: no hay autenticación ni FK a usuarios, así que cualquiera puede crear, modificar o borrar ratings de otro `user_id` | Preexistente. Los cambios de esta revisión no lo agravan | `spec/03_backend_security_review.md`, `CLAUDE.md` (problema conocido #9) |

## Resumen

| # | Hallazgo | Severidad | Confianza | Estado |
|---|---|---|---|---|
| — | Ninguno | — | — | — |

## Siguientes pasos

- [x] (Backend) Autenticación JWT y autorización por propietario en POST/PUT/DELETE de ratings, según `spec/03_backend_security_review.md`. Es el único riesgo de seguridad abierto del sistema de ratings.
- [ ] Repetir esta revisión con un diff real (por ejemplo `git diff` o un PR) antes de mergear. El análisis de hoy no pudo apoyarse en un diff.
