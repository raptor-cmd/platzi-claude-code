import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ratingsApi } from '../ratingsApi';

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });

const session = (user_id: number, token: string) => ({
  access_token: token,
  user_id,
  expires_in: 3600,
});

const RATING = {
  id: 1,
  course_id: 1,
  user_id: 1000000001,
  rating: 5,
  created_at: '2025-10-14T10:30:00',
  updated_at: '2025-10-14T10:30:00',
};

describe('ratingsApi anonymous session', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    window.localStorage.clear();
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('creates a session on first write and sends the token without user_id', async () => {
    fetchMock
      .mockResolvedValueOnce(json(session(1000000001, 'tok-1')))
      .mockResolvedValueOnce(json(RATING, 201));

    await ratingsApi.createRating(1, { rating: 5 });

    const [sessionUrl] = fetchMock.mock.calls[0];
    expect(sessionUrl).toContain('/auth/anonymous');

    const [, init] = fetchMock.mock.calls[1];
    expect(init.headers.Authorization).toBe('Bearer tok-1');
    expect(JSON.parse(init.body)).toEqual({ rating: 5 });
    expect(ratingsApi.getCurrentUserId()).toBe(1000000001);
  });

  it('reuses the stored session for later writes', async () => {
    fetchMock
      .mockResolvedValueOnce(json(session(1000000001, 'tok-1')))
      .mockResolvedValueOnce(json(RATING, 201))
      .mockResolvedValueOnce(json(RATING));

    await ratingsApi.createRating(1, { rating: 5 });
    await ratingsApi.updateRating(1, { rating: 4 });

    expect(fetchMock).toHaveBeenCalledTimes(3); // 1 sesión + 2 escrituras
    const [putUrl] = fetchMock.mock.calls[2];
    expect(putUrl).toContain('/courses/1/ratings/1000000001');
  });

  it('renews the session and retries once on 401', async () => {
    fetchMock
      .mockResolvedValueOnce(json(session(1000000001, 'tok-old')))
      .mockResolvedValueOnce(json({ detail: 'Invalid or expired token' }, 401))
      .mockResolvedValueOnce(json(session(1000000002, 'tok-new')))
      .mockResolvedValueOnce(json({ ...RATING, user_id: 1000000002 }, 201));

    const result = await ratingsApi.createRating(1, { rating: 5 });

    expect(result.user_id).toBe(1000000002);
    const [, retryInit] = fetchMock.mock.calls[3];
    expect(retryInit.headers.Authorization).toBe('Bearer tok-new');
  });

  it('deleteRating uses the session user_id in the path', async () => {
    fetchMock
      .mockResolvedValueOnce(json(session(1000000001, 'tok-1')))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));

    await ratingsApi.deleteRating(1);

    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toContain('/courses/1/ratings/1000000001');
    expect(init.method).toBe('DELETE');
  });
});
