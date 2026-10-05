# Plan de Implementación Frontend — Sistema de Ratings

**Alcance**: solo Frontend (Next.js 15 + React 19 + TypeScript strict). Parte de `spec/00_course_ratings_system.md` y fue verificado contra el código por el agente `frontend`.
**Estado de partida**: `StarRating` es solo lectura y se usa en el catálogo. `ratingsApi.ts` y `types/rating.ts` existen pero ningún componente los usa. El detalle del curso no muestra ratings y además está desalineado con la API.
**Reglas**: yarn, TypeScript strict (sin `any`), Vitest + RTL, SCSS + CSS Modules, camelCase / PascalCase. Comandos desde `Frontend/`. `yarn test` corre en modo watch, así que usar `yarn test --run`.

## Verificación de hallazgos

| # | Estado | Evidencia |
|---|---|---|
| F1 | Confirmado | `ratingsApi.ts:143` usa `/ratings/${userId}` y el backend expone `/ratings/user/{user_id}`. `handleApiResponse` exige `content-type` JSON y lanza `INVALID_FORMAT` con un 204. El `catch` solo mapea 404 a `null`. |
| F2 | Confirmado | `RatingStats` no tiene `rating_distribution`. `CourseDetail` no declara `rating_distribution`, `teacher_id` ni `classes[].name`. |
| F3 | Confirmado | `CourseDetail.tsx` usa `course.title`, `course.teacher`, `cls.title` y `cls.duration`. La API devuelve `name`, `teacher_id: number[]` y `classes[]` con `{id, name, description, slug}`, sin `duration`. Hoy la suma da `NaN` y se renderiza "NaNh NaNm". |
| F3b | Confirmado | `course/[slug]/page.tsx` no hace `await params`, `generateMetadata` usa `courseData.title` (undefined) y la URL `http://localhost:8000` está hardcodeada. Además, el fetch se repite en `generateMetadata` (2 requests por render). |
| F4 | Confirmado | `StarRating` declara `readonly` y lo ignora. No hay handlers ni foco, y tiene `role="img"`, así que no sirve como input. |
| F5 | Confirmado | `StarRating.tsx:34` repite `id="halfStarGradient"` en cada `StarIcon`. |
| F6 | Confirmado | No existe hook ni utilidad para `user_id`. |
| F7 | Confirmado | Solo hay tests de `StarRating`, `Course`, `VideoPlayer` y `classes/[class_id]/page`. Faltan `ratingsApi`, `RatingInput`, `CourseDetail` y el bloque de resumen. |

## Discrepancias spec vs código

1. **`user_id` es un entero positivo.** El spec dice "genera un `user_id`". El backend valida `int`, así que un UUID no sirve. El hook debe generar un entero.
2. **`rating_distribution` llega con claves string** (`"1"`..`"5"`). Hay que tiparlo como `Record<'1'|'2'|'3'|'4'|'5', number>` y leerlo con `String(n)`.
3. **El tipo `Class` mezcla dos contratos.** `GET /classes/{id}` devuelve `title`, `video` y `duration = 0`, pero el detalle del curso trae `{id, name, description, slug}`. Hay que separarlos y revisar `classes/[class_id]/page.tsx` y su test antes de tocar `Class`.
4. **No existe nombre de profesor.** La API devuelve solo IDs y no hay endpoint de teachers. Mostrar el nombre requeriría un cambio de backend, que hoy está fuera de alcance.
5. **`getRatingStats` captura 404 con stats vacías sin distribución.** El fallback debe incluir `rating_distribution` con ceros.
6. **La URL base está duplicada.** `ratingsApi` usa `NEXT_PUBLIC_API_URL` y `page.tsx` hardcodea `localhost:8000`.
7. **`CourseDetail` debe seguir siendo Server Component.** El bloque con `router.refresh()` va en un Client Component hijo.
8. **`thumbnail` puede ser nulo** en la DB. Verificar el modelo y manejar su ausencia.

## Orden y dependencias

`F1 → F2 → F3 → F4 → F5 → F6 → F7`. F1–F5 no dependen del Backend y pueden avanzar en paralelo con él. F2 debe estar lista antes de la UI nueva, para no montar ratings sobre un detalle con datos incorrectos.

**Del Backend se necesita**: B2 (204 válido) para la prueba real de `getUserRating` y antes de mergear F6; B1 (índice único) antes de exponer la UI a usuarios.

---

## Fase F1 — Cliente `ratingsApi` y tipos (F1, F2)

**Objetivo**: que el cliente use el contrato real y los tipos reflejen el JSON.

**Pasos**
1. `src/types/rating.ts`: añadir el tipo de distribución con claves string y extender `RatingStats` con `rating_distribution`. Actualizar `isRatingStats`. Comprobar en `schemas/rating.py` si `RatingStats` real incluye más campos.
2. `src/services/ratingsApi.ts`:
   - `getUserRating`: ruta `/ratings/user/${userId}`. Si el status es 204, devolver `null` antes de leer el body. Mantener 404 como `null`.
   - `handleApiResponse`: no exigir JSON en un 204. Parsear solo si hay `content-type` JSON. En errores sin JSON usar `HTTP <status>` en lugar de `INVALID_FORMAT`.
   - Fallback de `getRatingStats` con `rating_distribution` en ceros.
   - Quitar el header `Content-Type` en GET y DELETE (evita preflight CORS). Mantenerlo en POST y PUT.
3. Extraer la URL base a un módulo compartido que usen tanto el cliente como los Server Components.

**Tests** (nuevo `src/services/__tests__/ratingsApi.test.ts`, con `fetch` mockeado): ruta de `getUserRating`; 204 sin `content-type` → `null`; 404 → `null`; 200; `getRatingStats` y su fallback; POST 201 y PUT 200 con método y JSON correctos; DELETE 204 resuelve y 404 lanza `ApiError`; timeout (`AbortError` → `TIMEOUT`); error de red; 422 propaga `detail`.

**Verificación**: `yarn test --run ratingsApi` y `yarn lint`.

**Aceptación**: tests verdes, ninguna llamada usa `/ratings/{userId}`, sin `any`.

**Riesgos**: mientras B2 no esté corregido, un 204 puede llegar con `content-type` JSON y body inválido, por eso se evalúa el status antes de leer el body.

**Dependencias backend**: ninguna para desarrollar; B2 para la prueba manual.

---

## Fase F2 — Alinear `CourseDetail` con la API (F3, F2)

**Objetivo**: que el detalle muestre datos correctos antes de añadir UI nueva.

**Pasos**
1. `src/types/index.ts`:
   - Nuevo tipo para las clases del detalle con `id`, `name`, `description` y `slug`.
   - `CourseDetail` pasa a incluir `name`, `description`, `thumbnail`, `slug`, `teacher_id: number[]`, las clases del detalle, `average_rating`, `total_ratings` y `rating_distribution`.
   - Conservar `Class` solo si `/classes/[class_id]` lo usa (comprobar con grep).
2. `CourseDetail.tsx`: usar `name` y `cls.name`; quitar "Por <profesor>" y toda la lógica de duración (no inventar datos); manejar `thumbnail` nulo.
3. `course/[slug]/page.tsx`: `params` como `Promise` con `await` en la página y en `generateMetadata`; usar `name` en el título; usar la URL base compartida; deduplicar el fetch con `React.cache`.
4. `CourseDetail.module.scss`: eliminar estilos huérfanos de duración.

**Tests**
- Nuevo test de `CourseDetail`: renderiza `name`, descripción y clases por `name`; enlaces `/classes/{id}`; no muestra "NaN"; thumbnail ausente no rompe.
- Test de `page.tsx` siguiendo el patrón de `classes/[class_id]/page.test.tsx`: `generateMetadata` con `await params` y `name`; el 404 invoca `notFound`.

**Verificación**: `yarn test --run`, `yarn lint` y `yarn build` (valida los tipos de `params` de Next 15).

**Aceptación**: `/course/<slug>` real muestra título, clases y `<title>` correctos, y `yarn build` pasa sin errores de tipos.

**Riesgos**: quitar profesor y duración es un cambio visible; hay que confirmarlo. Los tests de `classes/[class_id]` dependen de `Class`.

**Dependencias backend**: ninguna.

---

## Fase F3 — `StarRating`: id único del gradiente (F5)

**Objetivo**: eliminar los ids duplicados en el DOM.

**Pasos**
1. En `StarRating.tsx`, generar un id único por estrella con `useId()` (limpiando los `:`) y referenciarlo en el relleno.
2. Renderizar el `<defs>` solo en la estrella media.

**Tests**: dos `StarRating` con rating 2.5 no producen ids duplicados, y el relleno de la estrella media referencia un id que existe.

**Verificación**: `yarn test --run StarRating` y `yarn lint`.

**Aceptación**: cero ids duplicados y sin regresión visual en el catálogo.

**Riesgos**: bajo. Los snapshots existentes cambian por el id.

**Dependencias**: ninguna.

---

## Fase F4 — Identidad provisional (F6)

**Objetivo**: un `user_id` entero estable por navegador.

**Pasos**
1. Nuevo hook `useUserId` (cliente), que devuelve `number | null`. Devuelve `null` en SSR y en el primer render, para evitar errores de hidratación.
2. Lee y guarda en `localStorage` dentro de `try/catch`. Si el valor no es un entero positivo, genera uno nuevo. Si el storage falla, lo conserva en memoria durante la sesión.
3. Comentar en el código que la identidad es provisional y manipulable (no hay autenticación).

**Tests** (`renderHook`): genera y persiste; reutiliza el existente; ignora valores inválidos (`"abc"`, `-1`, `0`); sobrevive a un `getItem` que lanza; mantiene el mismo id entre renders.

**Verificación**: `yarn test --run useUserId`.

**Aceptación**: entero positivo estable y sin warnings de hidratación en dev.

**Riesgos**: colisión de ids entre usuarios (baja). Otro navegador o dispositivo equivale a otro usuario. Documentarlo.

**Dependencias**: ninguna.

---

## Fase F5 — Componente `RatingInput` (F4)

**Objetivo**: input accesible para calificar de 1 a 5.

**Pasos**
1. Nuevo componente cliente `RatingInput` (con su `.module.scss`).
   - Props: valor actual, `onChange`, `disabled`, etiqueta accesible.
   - `role="radiogroup"` con 5 `role="radio"` y `aria-checked`. Solo uno es tabulable (roving tabindex).
   - Teclado: flechas, Home, End, Enter y Espacio. Hover con previsualización y foco visible.
2. Extraer `StarIcon` de `StarRating.tsx` para reutilizarlo.
3. Eliminar la prop muerta `readonly` de `StarRating` y actualizar usos y tests con grep.

**Tests**: roles y `aria-checked`; click llama a `onChange(n)`; navegación con flechas, Home y End; `disabled` no emite; hover muestra la vista previa; un solo elemento tabulable. Usar `fireEvent`, o `user-event` solo si ya está en `package.json` (no añadir dependencias sin avisar).

**Verificación**: `yarn test --run RatingInput` y `yarn lint`.

**Aceptación**: operable solo con teclado y conforme al patrón WAI-ARIA de radiogroup.

**Dependencias**: F3 (ids de gradiente).

---

## Fase F6 — Resumen y mutaciones (F2, F4, F6)

**Objetivo**: ver promedio, total y distribución, y poder calificar, editar y borrar el rating propio.

**Pasos**
1. `RatingSummary` (presentacional, compatible con Server Component): promedio con `StarRating`, total, cinco barras de distribución (5 a 1) con porcentaje y estado vacío "Aún sin calificaciones". Lee la distribución con `String(n)`.
2. `UserRating` (componente cliente), usando `useUserId` y `useRouter`:
   - Al montar, `getUserRating` carga el rating propio (`null` si no hay). Estados `loading | error | success`.
   - Calificar con POST (upsert), que sirve para crear y editar y evita el 404 por carrera. Borrar con DELETE.
   - Actualización optimista con rollback si falla, mensaje de error con `role="alert"` y `router.refresh()` tras cada éxito (los datos del servidor son `no-store`).
   - Entrada deshabilitada mientras hay una petición pendiente, para evitar clics rápidos.
3. Integrar ambos en `CourseDetail.tsx` pasando `course.id` y los stats. `CourseDetail` sigue siendo Server Component.
4. Estilos con SCSS modules y las variables de `src/styles/vars.scss`, responsive.

**Tests**
- `RatingSummary`: promedio, total, anchos de barras, estado vacío y distribución con claves string.
- `UserRating` (con `ratingsApi`, `next/navigation` y `useUserId` mockeados): carga inicial con y sin rating; click crea y llama a `router.refresh`; un fallo hace rollback y muestra `alert`; borrar llama a DELETE y limpia; `userId` nulo deshabilita la entrada.
- `CourseDetail` incluye ambas secciones.

**Verificación**: `yarn test --run`, `yarn lint` y `yarn build`.

**Aceptación**: tras calificar, el detalle muestra el nuevo promedio sin recarga manual, y el catálogo muestra el mismo promedio al volver.

**Riesgos**: `router.refresh()` no reinicia el estado del cliente, así que hay que alinearlo con las props nuevas. Validar a mano el cache de navegación de Next 15.

**Dependencias backend**: B2 antes de mergear esta fase; B1 antes de exponerla a usuarios.

---

## Fase F7 — Calidad frontend

1. `yarn lint && yarn test --run && yarn build`.
2. Revisar el enlace "Regresar al curso" de `/classes/[class_id]`, que apunta a `/course` (deuda técnica #4). Corregirlo si se aprueba incluirlo en el alcance.

---

## Verificación final

Con el backend arriba (`make start` en `Backend/`) y `yarn dev` en `http://localhost:3000`:

1. Calificar, editar y borrar; recargar para comprobar que el `user_id` persiste.
2. Catálogo y detalle muestran el mismo promedio.
3. Probar con `localStorage` bloqueado, solo con teclado y en ancho móvil.
4. Backend caído: se muestran `error.tsx` del detalle y los errores del input.
5. Consola sin warnings de hidratación ni ids duplicados.

## Decisiones a confirmar

1. Quitar "Por <profesor>" y la duración del detalle hasta que el backend los exponga (recomendado).
2. Eliminar la prop `readonly` de `StarRating` (recomendado, la reemplaza `RatingInput`).
3. Incluir en el alcance el enlace "Regresar al curso" y la URL base compartida (la URL base ya está en F1).

## Fuera de alcance

Apps móviles, autenticación real, reseñas con texto, nombres de profesores y duración por clase (requieren cambios de backend).
