import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type HttpModule = typeof import('@/api/http-init');

const okEnvelope = (obj: unknown = {}): Response =>
  new Response(JSON.stringify({ success: true, msg: '', obj }), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });

const csrfResponse = (token: string): Response =>
  new Response(JSON.stringify({ success: true, obj: token }), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });

describe('http-init fetch wrapper', () => {
  let http: HttpModule;
  let fetchMock: ReturnType<typeof vi.fn>;
  let replaceMock: ReturnType<typeof vi.fn>;

  const initOf = (call = 0): RequestInit => fetchMock.mock.calls[call][1] as RequestInit;
  const urlOf = (call = 0): string => fetchMock.mock.calls[call][0] as string;
  const headersOf = (call = 0): Headers => initOf(call).headers as Headers;

  beforeEach(async () => {
    vi.resetModules();
    document.head.innerHTML = '';
    delete (window as { X_UI_BASE_PATH?: string }).X_UI_BASE_PATH;
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    replaceMock = vi.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        replace: replaceMock,
        href: 'http://localhost/',
        origin: 'http://localhost',
        pathname: '/',
      },
    });
    http = await import('@/api/http-init');
  });

  afterEach(() => {
    delete window.X_UI_TG_MINIAPP_MODE;
    vi.unstubAllGlobals();
  });

  it('form-encodes bodies and repeats array keys', async () => {
    document.head.innerHTML = '<meta name="csrf-token" content="tok">';
    http.setupHttp();
    fetchMock.mockResolvedValue(okEnvelope());

    await http.httpRequest('POST', '/panel/x', { a: 1, b: ['x', 'y'] });

    expect(initOf().body).toBe('a=1&b=x&b=y');
    expect(headersOf().get('content-type')).toBe(
      'application/x-www-form-urlencoded; charset=UTF-8',
    );
  });

  it('JSON-encodes bodies when the caller declares application/json', async () => {
    document.head.innerHTML = '<meta name="csrf-token" content="tok">';
    http.setupHttp();
    fetchMock.mockResolvedValue(okEnvelope());

    await http.httpRequest(
      'POST',
      '/panel/x',
      { a: 1 },
      { headers: { 'Content-Type': 'application/json' } },
    );

    expect(initOf().body).toBe(JSON.stringify({ a: 1 }));
    expect(headersOf().get('content-type')).toBe('application/json');
  });

  it('passes FormData through without a Content-Type header', async () => {
    document.head.innerHTML = '<meta name="csrf-token" content="tok">';
    http.setupHttp();
    fetchMock.mockResolvedValue(okEnvelope());

    const fd = new FormData();
    fd.append('db', 'contents');
    await http.httpRequest('POST', '/panel/import', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });

    expect(initOf().body).toBe(fd);
    expect(headersOf().has('content-type')).toBe(false);
  });

  it('attaches the CSRF token on POST and omits it on GET', async () => {
    document.head.innerHTML = '<meta name="csrf-token" content="tok">';
    http.setupHttp();
    fetchMock.mockImplementation(() => Promise.resolve(okEnvelope()));

    await http.httpRequest('POST', '/p', { a: 1 });
    expect(headersOf().get('X-CSRF-Token')).toBe('tok');
    expect(headersOf().get('X-Requested-With')).toBe('XMLHttpRequest');

    fetchMock.mockClear();
    await http.httpRequest('GET', '/g');
    expect(headersOf().get('X-CSRF-Token')).toBeNull();
    expect(headersOf().get('X-Requested-With')).toBe('XMLHttpRequest');
  });

  it('prepends the base path to request and csrf-token URLs', async () => {
    window.X_UI_BASE_PATH = '/xui';
    http.setupHttp();
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve(url.endsWith('/csrf-token') ? csrfResponse('fresh') : okEnvelope()),
    );

    await http.httpRequest('POST', '/panel/api/x', { a: 1 });

    expect(urlOf(0)).toBe('/xui/csrf-token');
    expect(urlOf(1)).toBe('/xui/panel/api/x');
  });

  it('refreshes the token and retries once on 403', async () => {
    http.setupHttp();
    let dataCalls = 0;
    fetchMock.mockImplementation((url: string) => {
      if (url.endsWith('/csrf-token')) return Promise.resolve(csrfResponse(`tok${dataCalls}`));
      dataCalls += 1;
      return Promise.resolve(dataCalls === 1 ? new Response('', { status: 403 }) : okEnvelope());
    });

    const resp = await http.httpRequest('POST', '/panel/api/x', { a: 1 });

    expect(resp.ok).toBe(true);
    expect(dataCalls).toBe(2);
    expect(headersOf(3).get('X-CSRF-Token')).toBe('tok1');
  });

  it('throws HttpError when the retried request is still 403', async () => {
    http.setupHttp();
    let dataCalls = 0;
    fetchMock.mockImplementation((url: string) => {
      if (url.endsWith('/csrf-token')) return Promise.resolve(csrfResponse('tok'));
      dataCalls += 1;
      return Promise.resolve(new Response('', { status: 403 }));
    });

    await expect(http.httpRequest('POST', '/panel/api/x', { a: 1 })).rejects.toBeInstanceOf(
      http.HttpError,
    );
    expect(dataCalls).toBe(2);
  });

  it('redirects once on 401 and cancels subsequent requests', async () => {
    window.X_UI_BASE_PATH = '/xui';
    http.setupHttp();
    fetchMock.mockResolvedValue(new Response('', { status: 401 }));

    await expect(http.httpRequest('GET', '/p')).rejects.toMatchObject({ name: 'AbortError' });
    await expect(http.httpRequest('POST', '/p')).rejects.toMatchObject({ name: 'AbortError' });
    expect(replaceMock).toHaveBeenCalledExactlyOnceWith('/xui');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('never replays a Mini App write after a 403', async () => {
    window.X_UI_TG_MINIAPP_MODE = true;
    document.head.innerHTML = '<meta name="csrf-token" content="synthetic">';
    http.setupHttp();
    fetchMock.mockResolvedValueOnce(new Response('', { status: 403 }));
    await expect(http.httpRequest('POST', '/panel/api/x', { a: 1 })).rejects.toMatchObject({ status: 403 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('ignores late success and stops sending new requests after Mini App expiry', async () => {
    window.X_UI_TG_MINIAPP_MODE = true;
    http.setupHttp();
    let finish!: (response: Response) => void;
    fetchMock.mockImplementationOnce(() => new Promise<Response>((resolve) => { finish = resolve; }));
    fetchMock.mockResolvedValueOnce(new Response('', { status: 401 }));
    const old = expect(http.httpRequest('GET', '/panel/api/old')).rejects.toMatchObject({ name: 'AbortError' });
    await expect(http.httpRequest('GET', '/panel/api/expiry')).rejects.toMatchObject({ name: 'AbortError' });
    await old;
    expect(initOf(0).signal?.aborted).toBe(true);
    expect(replaceMock).toHaveBeenCalledExactlyOnceWith('/?signedOut=1');
    finish(okEnvelope());
    http.setupHttp();
    await expect(http.httpRequest('POST', '/panel/api/new')).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('cancels queued writes during logout even while CSRF is loading', async () => {
    window.X_UI_TG_MINIAPP_MODE = true;
    http.setupHttp();
    let finish!: (response: Response) => void;
    fetchMock.mockImplementationOnce(() => new Promise<Response>((resolve) => { finish = resolve; }));
    const writes = ['/first', '/second'].map((url) =>
      expect(http.httpRequest('POST', url)).rejects.toMatchObject({ name: 'AbortError' }),
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
    http.leaveMiniAppSession();
    await Promise.all(writes);
    expect(initOf().signal?.aborted).toBe(true);
    finish(okEnvelope('synthetic'));
    await Promise.resolve();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('parses empty, 204, non-JSON, and malformed bodies tolerantly', async () => {
    http.setupHttp();

    fetchMock.mockResolvedValueOnce(new Response('', { status: 200 }));
    expect((await http.httpRequest('GET', '/a')).data).toBe('');

    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    expect((await http.httpRequest('GET', '/b')).data).toBe('');

    fetchMock.mockResolvedValueOnce(
      new Response('hello', { status: 200, headers: { 'content-type': 'text/plain' } }),
    );
    expect((await http.httpRequest('GET', '/c')).data).toBe('hello');

    fetchMock.mockResolvedValueOnce(
      new Response('{bad', { status: 200, headers: { 'content-type': 'application/json' } }),
    );
    expect((await http.httpRequest('GET', '/d')).data).toBe('{bad');
  });

  it('rejects when fetch fails at the network level', async () => {
    http.setupHttp();
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));

    await expect(http.httpRequest('GET', '/x')).rejects.toThrow('Failed to fetch');
  });

  it('passes an AbortSignal when a timeout is set', async () => {
    http.setupHttp();
    fetchMock.mockResolvedValue(okEnvelope());

    await http.httpRequest('GET', '/x', undefined, { timeout: 50 });

    expect(initOf().signal).toBeInstanceOf(AbortSignal);
  });

  it('cancels an active request when the caller aborts before its timeout', async () => {
    http.setupHttp();
    fetchMock.mockImplementation(() => new Promise(() => {}));
    const controller = new AbortController();
    const request = expect(
      http.httpRequest('GET', '/x', undefined, { timeout: 1_000, signal: controller.signal }),
    ).rejects.toMatchObject({ name: 'AbortError' });
    controller.abort();
    await request;
    expect(initOf().signal?.aborted).toBe(true);
  });

  it('times out response body reads even when a caller signal is present', async () => {
    http.setupHttp();
    const response = new Response('');
    vi.spyOn(response, 'text').mockImplementation(() => new Promise(() => {}));
    fetchMock.mockResolvedValue(response);
    const controller = new AbortController();
    await expect(
      http.httpRequest('GET', '/x', undefined, { timeout: 20, signal: controller.signal }),
    ).rejects.toMatchObject({ name: 'TimeoutError' });
    expect(initOf().signal?.aborted).toBe(true);
    expect(controller.signal.aborted).toBe(false);
  });

  it.each([
    ['/x?keep=1', '/x?keep=1&added=yes'],
    ['/x?', '/x?added=yes'],
    ['/x#frag', '/x?added=yes#frag'],
    ['/x?keep=1#frag', '/x?keep=1&added=yes#frag'],
  ])('appends encoded params to %s', async (url, expected) => {
    http.setupHttp();
    fetchMock.mockResolvedValue(okEnvelope());

    await http.httpRequest('GET', url, undefined, { params: { added: 'yes' } });

    expect(urlOf()).toBe(expected);
  });

  it('preserves the URL when no params are supplied', async () => {
    http.setupHttp();
    fetchMock.mockResolvedValue(okEnvelope());

    await http.httpRequest('GET', '/x?keep=1#frag');

    expect(urlOf()).toBe('/x?keep=1#frag');
  });
});
