import type { ReactNode } from 'react';
import { renderHook, waitFor, act, fireEvent, screen } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useClients } from '@/hooks/useClients';
import { makeTestQueryClient, renderWithProviders } from '@/test/test-utils';
import { MemoryRouter } from 'react-router';
import ClientsPage from '@/pages/clients/ClientsPage';
import { HttpUtil, Msg } from '@/utils';

vi.mock('@/layouts/AppSidebar', () => ({ default: () => null }));

afterEach(() => {
  vi.restoreAllMocks();
});

const emptyPage = {
  items: [],
  total: 0,
  filtered: 0,
  page: 1,
  pageSize: 25,
  groups: [],
  summary: {
    total: 0,
    active: 0,
    onlineCount: 0,
    depletedCount: 0,
    expiringCount: 0,
    deactiveCount: 0,
    online: [],
    depleted: [],
    expiring: [],
    deactive: [],
  },
};

function mockPanel(defaults: Record<string, unknown>) {
  const pagedUrls: string[] = [];
  vi.spyOn(HttpUtil, 'get').mockImplementation(async (url: string) => {
    if (url.includes('/clients/list/paged')) {
      pagedUrls.push(url);
      return new Msg(true, '', emptyPage);
    }
    if (url.includes('/inbounds/options')) return new Msg(true, '', []);
    return new Msg(true, '', null);
  });
  vi.spyOn(HttpUtil, 'post').mockImplementation(async (url: string) => {
    if (url.includes('/setting/defaultSettings')) return new Msg(true, '', defaults);
    if (url.includes('/clients/onlines')) return new Msg(true, '', []);
    return new Msg(true, '', null);
  });
  return pagedUrls;
}

function wrapperFor() {
  const queryClient = makeTestQueryClient();
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('client filter persistence in a WebView', () => {
  afterEach(() => localStorage.removeItem('clientsFilterState'));

  it('restores search after reopening the client page', async () => {
    mockPanel({ pageSize: 25 });
    const page = <MemoryRouter><ClientsPage /></MemoryRouter>;
    const first = renderWithProviders(page);
    const search = await screen.findByRole('textbox', { name: 'Search' });
    fireEvent.change(search, { target: { value: 'synthetic-filter' } });
    first.unmount();
    renderWithProviders(page);
    expect(await screen.findByDisplayValue('synthetic-filter')).toBeTruthy();
  });

  it('can still search when browser storage cannot save preferences', async () => {
    const original = Storage.prototype.setItem;
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function (this: Storage, key, value) {
      if (key === 'clientsFilterState') throw new DOMException('Synthetic storage policy', 'SecurityError');
      original.call(this, key, value);
    });
    const urls = mockPanel({ pageSize: 25 });
    renderWithProviders(<MemoryRouter><ClientsPage /></MemoryRouter>);
    const search = await screen.findByRole('textbox', { name: 'Search' });
    fireEvent.change(search, { target: { value: 'synthetic-filter' } });
    await waitFor(() => expect(urls.some((url) => url.includes('synthetic-filter'))).toBe(true));
  });
});

describe('useClients query gating', () => {
  it.each([
    ['missing', {}, false],
    ['false', { happLinkEnable: false }, false],
    ['true', { happLinkEnable: true }, true],
  ])('maps a %s Happ gate to a fail-closed client setting', async (_name, defaults, want) => {
    mockPanel(defaults);
    const { result } = renderHook(() => useClients(), { wrapper: wrapperFor() });

    await waitFor(() => expect(result.current.settingsReady).toBe(true));
    expect(result.current.subSettings.happLinkEnable).toBe(want);
  });

  it('does not fetch the list until the page supplies a query', async () => {
    const pagedUrls = mockPanel({ pageSize: 25 });
    const { result } = renderHook(() => useClients(), { wrapper: wrapperFor() });

    await waitFor(() => expect(result.current.settingsReady).toBe(true));
    // The page has not called setQuery yet, so nothing should have gone out —
    // this is what used to cost a thrown-away round trip on every page load.
    expect(pagedUrls).toEqual([]);
    expect(result.current.fetched).toBe(false);
  });

  it('issues exactly one request for a page load that settles on one query', async () => {
    const pagedUrls = mockPanel({ pageSize: 50 });
    const { result } = renderHook(() => useClients(), { wrapper: wrapperFor() });

    await waitFor(() => expect(result.current.settingsReady).toBe(true));
    act(() => {
      result.current.setQuery({ page: 1, pageSize: 50, sort: 'createdAt', order: 'ascend' });
    });

    await waitFor(() => expect(result.current.fetched).toBe(true));
    expect(pagedUrls).toHaveLength(1);
    expect(pagedUrls[0]).toContain('pageSize=50');
    expect(pagedUrls[0]).toContain('sort=createdAt');
  });

  it('fetches as soon as a query arrives, without waiting for the settings', async () => {
    // The page remembers the previous visit's page size in localStorage, so on a
    // return visit it can supply a query on the first render. The hook must not
    // hold that back behind /setting/defaultSettings, or the two round trips
    // serialise and the list lands ~160ms later than it needs to.
    const pagedUrls = mockPanel({ pageSize: 25 });
    const { result } = renderHook(() => useClients(), { wrapper: wrapperFor() });

    act(() => {
      result.current.setQuery({ page: 1, pageSize: 25, sort: 'createdAt', order: 'ascend' });
    });
    await waitFor(() => expect(pagedUrls).toHaveLength(1));
  });

  it('reports settingsReady even when the settings request fails, so the page can still render', async () => {
    vi.spyOn(HttpUtil, 'get').mockImplementation(
      async (url: string) => new Msg(true, '', url.includes('/inbounds/options') ? [] : emptyPage),
    );
    vi.spyOn(HttpUtil, 'post').mockResolvedValue(new Msg(false, 'boom', null));
    const { result } = renderHook(() => useClients(), { wrapper: wrapperFor() });

    await waitFor(() => expect(result.current.settingsReady).toBe(true));
  });

  it('skips the list, options and onlines queries for mutation-only callers', async () => {
    const pagedUrls = mockPanel({ pageSize: 25 });
    const postSpy = vi.mocked(HttpUtil.post);
    const { result } = renderHook(() => useClients({ list: false }), { wrapper: wrapperFor() });

    await waitFor(() => expect(result.current.settingsReady).toBe(true));
    act(() => {
      result.current.setQuery({ page: 1, pageSize: 25, sort: 'createdAt', order: 'ascend' });
    });

    await waitFor(() => expect(result.current.settingsReady).toBe(true));
    expect(pagedUrls).toEqual([]);
    // subSettings still needs defaultSettings; onlines must not be polled.
    const posted = postSpy.mock.calls.map((c) => String(c[0]));
    expect(posted.some((u) => u.includes('/setting/defaultSettings'))).toBe(true);
    expect(posted.some((u) => u.includes('/clients/onlines'))).toBe(false);
    expect(vi.mocked(HttpUtil.get).mock.calls.map((c) => String(c[0]))).toEqual([]);
  });
});
