/**
 * Ratings API Service
 * Maneja todas las peticiones HTTP relacionadas con el sistema de ratings
 */

import type { CourseRating, RatingRequest, RatingStats } from '@/types/rating';
import { ApiError } from '@/types/rating';

// Base URL del backend API
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Opciones extendidas de fetch con timeout
interface FetchOptions extends RequestInit {
  timeout?: number;
}

/**
 * Helper: Fetch con timeout para prevenir requests colgados
 */
async function fetchWithTimeout(
  url: string,
  options: FetchOptions = {}
): Promise<Response> {
  const { timeout = 10000, ...fetchOptions } = options;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      ...fetchOptions,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);
    return response;
  } catch (error) {
    clearTimeout(timeoutId);

    if (error instanceof Error) {
      if (error.name === 'AbortError') {
        throw new ApiError('Request timeout', 408, 'TIMEOUT');
      }
      throw new ApiError(
        `Network error: ${error.message}`,
        0,
        'NETWORK_ERROR'
      );
    }

    throw new ApiError('Unknown error occurred', 0, 'UNKNOWN');
  }
}

/**
 * Helper: Procesa la respuesta de la API y maneja errores
 */
async function handleApiResponse<T>(response: Response): Promise<T> {
  const contentType = response.headers.get('content-type');

  // Verificar que sea JSON
  if (!contentType || !contentType.includes('application/json')) {
    throw new ApiError(
      'Invalid response format',
      response.status,
      'INVALID_FORMAT'
    );
  }

  // Parsear el body
  const data = await response.json();

  // Si la respuesta no es OK, lanzar error con detalles
  if (!response.ok) {
    const message = data.detail || data.message || `HTTP ${response.status}`;
    throw new ApiError(message, response.status, data.code, data);
  }

  return data as T;
}

// ==================== Sesión anónima ====================

const SESSION_KEY = 'platziflix_anon_session';

interface AnonymousSession {
  access_token: string;
  user_id: number;
  expires_at: number; // epoch ms
}

function readSession(): AnonymousSession | null {
  try {
    const raw = window.localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw) as AnonymousSession;
    // Descartar si le queda menos de 1 minuto de vida
    return session.expires_at - Date.now() > 60_000 ? session : null;
  } catch {
    return null;
  }
}

async function createSession(): Promise<AnonymousSession> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/auth/anonymous`, {
    method: 'POST',
  });
  const data = await handleApiResponse<{
    access_token: string;
    user_id: number;
    expires_in: number;
  }>(response);

  const session: AnonymousSession = {
    access_token: data.access_token,
    user_id: data.user_id,
    expires_at: Date.now() + data.expires_in * 1000,
  };
  try {
    window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  } catch {
    // Sin localStorage la sesión dura solo esta llamada
  }
  return session;
}

/**
 * Devuelve la sesión anónima vigente o crea una nueva.
 * Solo funciona en el navegador (usa localStorage).
 */
async function getSession(forceNew = false): Promise<AnonymousSession> {
  if (!forceNew) {
    const existing = readSession();
    if (existing) return existing;
  }
  return createSession();
}

/** user_id de la sesión actual, o null si aún no hay sesión. */
function getCurrentUserId(): number | null {
  return typeof window === 'undefined' ? null : readSession()?.user_id ?? null;
}

/**
 * Fetch autenticado con el token de la sesión anónima.
 * Si el backend responde 401 (token vencido), renueva la sesión y reintenta una vez.
 */
async function authFetch(
  buildUrl: (userId: number) => string,
  options: FetchOptions = {}
): Promise<Response> {
  const send = async (session: AnonymousSession) =>
    fetchWithTimeout(buildUrl(session.user_id), {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${session.access_token}`,
      },
    });

  const response = await send(await getSession());
  if (response.status !== 401) return response;
  return send(await getSession(true));
}

/**
 * GET /courses/{course_id}/ratings/stats
 * Obtiene las estadísticas de ratings de un curso
 */
async function getRatingStats(courseId: number): Promise<RatingStats> {
  const url = `${API_BASE_URL}/courses/${courseId}/ratings/stats`;

  try {
    const response = await fetchWithTimeout(url, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    return await handleApiResponse<RatingStats>(response);
  } catch (error) {
    // Si el curso no tiene ratings (404), retornar stats vacías
    if (error instanceof ApiError && error.status === 404) {
      return {
        average_rating: 0,
        total_ratings: 0,
      };
    }
    throw error;
  }
}

/**
 * GET /courses/{course_id}/ratings
 * Obtiene todos los ratings de un curso
 */
async function getCourseRatings(courseId: number): Promise<CourseRating[]> {
  const url = `${API_BASE_URL}/courses/${courseId}/ratings`;

  try {
    const response = await fetchWithTimeout(url, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    return await handleApiResponse<CourseRating[]>(response);
  } catch (error) {
    // Si no hay ratings (404), retornar array vacío
    if (error instanceof ApiError && error.status === 404) {
      return [];
    }
    throw error;
  }
}

/**
 * GET /courses/{course_id}/ratings/{user_id}
 * Obtiene el rating de un usuario específico para un curso
 */
async function getUserRating(
  courseId: number,
  userId: number
): Promise<CourseRating | null> {
  const url = `${API_BASE_URL}/courses/${courseId}/ratings/${userId}`;

  try {
    const response = await fetchWithTimeout(url, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    return await handleApiResponse<CourseRating>(response);
  } catch (error) {
    // Si el usuario no ha calificado (404), retornar null
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

/**
 * POST /courses/{course_id}/ratings
 * Crea un nuevo rating para un curso
 */
async function createRating(
  courseId: number,
  request: RatingRequest
): Promise<CourseRating> {
  // El user_id lo define el token; no se envía en el body
  const { rating } = request;
  const response = await authFetch(
    () => `${API_BASE_URL}/courses/${courseId}/ratings`,
    { method: 'POST', body: JSON.stringify({ rating }) }
  );

  return await handleApiResponse<CourseRating>(response);
}

/**
 * PUT /courses/{course_id}/ratings/{user_id}
 * Actualiza el rating existente de la sesión actual
 */
async function updateRating(
  courseId: number,
  request: RatingRequest
): Promise<CourseRating> {
  const { rating } = request;
  const response = await authFetch(
    (userId) => `${API_BASE_URL}/courses/${courseId}/ratings/${userId}`,
    { method: 'PUT', body: JSON.stringify({ rating }) }
  );

  return await handleApiResponse<CourseRating>(response);
}

/**
 * DELETE /courses/{course_id}/ratings/{user_id}
 * Elimina el rating de la sesión actual
 */
async function deleteRating(courseId: number): Promise<void> {
  const response = await authFetch(
    (userId) => `${API_BASE_URL}/courses/${courseId}/ratings/${userId}`,
    { method: 'DELETE' }
  );

  // 204 No Content es exitoso
  if (response.status !== 204 && !response.ok) {
    await handleApiResponse<void>(response);
  }
}

// Export del servicio como objeto constante
export const ratingsApi = {
  getRatingStats,
  getCourseRatings,
  getUserRating,
  getCurrentUserId,
  createRating,
  updateRating,
  deleteRating,
} as const;

// Export de ApiError para manejo en componentes
export { ApiError };
