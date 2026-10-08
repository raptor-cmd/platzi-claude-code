# Platziflix

plataforma online de cursos, cada cursos tiene clases, descripciones y no hay mucho mas, eso es el inicio.

## Stacks

### Frontend
- Typescript
- CSS modules
- SASS

### Mobile
- iOS:
    - Swift
    - SwiftUI
- Android:
    - Kotlin
    - Jetpack Compose

### Backend
- Python
- FastAPI
- PostgreSQl

## Contratos

### Entidades
1. Curso
2. Clases
3. Profesor

### Contratos


- Course
```json
{
    "id": 1,
    "name": "Curso de React",
    "description": "Curso de React",
    "thumbnail": "https://via.placeholder.com/150", 
    "slug": "curso-de-react",
    "created_at": "2021-01-01",
    "updated_at": "2021-01-01",
    "deleted_at": "2021-01-01",
    "teacher_id": [1, 2, 3]
}
```

- Clases:
```json
{
    "id": 1, 
    "course_id": 1, 
    "name": "Clase 1",
    "description": "Clase 1",
    "slug": "clase-1",
    "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "created_at": "2021-01-01",
    "updated_at": "2021-01-01",
    "deleted_at": "2021-01-01"
}
```

- Teacher
```json
{
    "id": 1,
    "name": "John Doe",
    "email": "john.doe@example.com",
    "created_at": "2021-01-01",
    "updated_at": "2021-01-01",
    "deleted_at": "2021-01-01"
}
```

### Endpoints

- GET /courses -> Listar todos los cursos
```json
[
    {
        "id": 1,
        "name": "Curso de React",
        "description": "Curso de React",
        "thumbnail": "https://via.placeholder.com/150", 
        "slug": "curso-de-react",
        "average_rating": 4.33,
        "total_ratings": 3
    }
]
```
`average_rating` es un `float` redondeado a 2 decimales (`0.0` si no hay ratings) y `total_ratings` un `int` (`0` si no hay ratings). Los cursos sin ratings siempre aparecen en el listado. Orden estable por `id`.

- GET /courses/:slug -> Obtener un curso
```json
{
    "id": 1,
    "name": "Curso de React",
    "description": "Curso de React",
    "thumbnail": "https://via.placeholder.com/150", 
    "slug": "curso-de-react",
    "teacher_id": [1, 2, 3],
    "classes": [
        {
            "id": 1,
            "name": "Clase 1",
            "description": "Clase 1",
            "slug": "clase-1"
        }
    ],
    "average_rating": 4.33,
    "total_ratings": 3,
    "rating_distribution": {"1": 0, "2": 0, "3": 1, "4": 1, "5": 1}
}
```
- `teacher_id` es solo la lista de ids (no incluye nombres de profesores).
- `classes[]` trae únicamente `id`, `name`, `description` y `slug` (sin duración ni video).
- `rating_distribution`: las claves son los valores 1..5 y **viajan como strings** en JSON (`"1"`..`"5"`), aunque en el backend sean enteros. Los clientes deben parsearlas como tales.
- 404 `{"detail": "Course not found"}` si el slug no existe.

- GET /courses/:slug/classes/:id -> Obtener una clase
```json
{
    "id": 1,
    "name": "Clase 1",
    "description": "Clase 1",
    "slug": "clase-1",
    "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "created_at": "2021-01-01",
    "updated_at": "2021-01-01",
    "deleted_at": "2021-01-01"
}
```

> **Discrepancia contrato vs implementación**: el contrato define `/courses/:slug/classes/:id`, pero el backend expone `GET /classes/{class_id}` (lee de `Lesson`). Su respuesta real es:
> ```json
> {
>     "id": 1,
>     "title": "Clase 1",
>     "description": "Clase 1",
>     "slug": "clase-1",
>     "video": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
>     "duration": 0
> }
> ```
> `duration` es siempre `0` (TODO). Se documenta tal cual; **no se cambia la ruta sin avisar a los tres clientes** (web, Android e iOS). 404 `{"detail": "Class not found"}` si no existe.

## Ratings

Notas generales:
- **No hay autenticación**: el `user_id` lo envía el cliente y no es una identidad confiable. Tampoco hay FK a usuarios.
- Un solo rating **activo** por `(course_id, user_id)`, garantizado en base de datos por un índice único parcial (`WHERE deleted_at IS NULL`). Los ratings eliminados (soft delete) no cuentan y pueden convivir varios.
- Rating válido: entero de 1 a 5.
- Los errores de negocio responden `{"detail": "<mensaje>"}`. Los errores de validación de FastAPI (422) usan su formato estándar.
- Ojo con las rutas: `GET` usa `/ratings/user/{user_id}`, mientras que `PUT` y `DELETE` usan `/ratings/{user_id}`.

Objeto rating (`RatingResponse`):
```json
{
    "id": 123,
    "course_id": 1,
    "user_id": 42,
    "rating": 5,
    "created_at": "2025-10-14T10:30:00",
    "updated_at": "2025-10-14T10:30:00"
}
```

- POST /courses/:course_id/ratings -> Crear o actualizar el rating de un usuario (upsert)
```json
{
    "user_id": 42,
    "rating": 5
}
```
    - `user_id` entero positivo; `rating` entre 1 y 5.
    - **201** con el objeto rating, tanto al crear como al actualizar uno activo existente (el código no distingue ambos casos).
    - 404 si el curso no existe.
    - 422 si falta un campo, el tipo es incorrecto o falla la validación del schema, incluido `rating` fuera de 1–5 y `user_id <= 0`. El servicio también valida el rango y lanzaría 400, pero por HTTP la validación del schema responde antes, así que ese 400 no es alcanzable hoy.

- GET /courses/:course_id/ratings -> Listar ratings activos, más nuevos primero
    - 200 con una lista de objetos rating (vacía si no hay).
    - 404 si el curso no existe.

- GET /courses/:course_id/ratings/stats -> Estadísticas
```json
{
    "average_rating": 4.35,
    "total_ratings": 142,
    "rating_distribution": {"1": 5, "2": 10, "3": 25, "4": 50, "5": 52}
}
```
    - 200. Las claves de `rating_distribution` viajan como strings.
    - 404 si el curso no existe.

- GET /courses/:course_id/ratings/user/:user_id -> Rating de un usuario
    - 200 con el objeto rating si el usuario ya calificó.
    - **204 sin body** si no ha calificado (incluye el caso de rating eliminado). Los clientes deben tratarlo como "sin rating" (`null`) y no intentar parsear JSON.

- PUT /courses/:course_id/ratings/:user_id -> Actualizar un rating existente
```json
{
    "user_id": 42,
    "rating": 3
}
```
    - 200 con el objeto rating actualizado.
    - 400 si el `user_id` del body difiere del path.
    - 404 si el usuario no tiene un rating activo en ese curso (para crear se usa `POST`).
    - 422 por validación del schema.

- DELETE /courses/:course_id/ratings/:user_id -> Eliminar (soft delete)
    - 204 sin body.
    - 404 si no existe un rating activo.
