import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { MiniAppEntry } from '@/entries/miniapp';

afterEach(() => {
  window.history.replaceState(null, '', '/');
  delete window.Telegram;
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

test('signed-out landing does not submit initData from the same WebView', async () => {
  window.history.replaceState(null, '', '/?signedOut=1');
  window.Telegram = { WebApp: { initData: 'synthetic-fixture' } };
  const fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
  render(<MiniAppEntry />);
  expect(await screen.findByText(/会话已结束/)).toBeTruthy();
  expect(fetchMock).not.toHaveBeenCalled();
});

test('retry refreshes CSRF and ignores a late response from the timed-out attempt', async () => {
  vi.useFakeTimers();
  window.Telegram = { WebApp: { initData: 'synthetic-fixture' } };
  let finishFirst!: (response: Response) => void;
  const fetchMock = vi.fn<(url: string, options: RequestInit) => Promise<Response>>()
    .mockImplementationOnce(() => new Promise((resolve) => { finishFirst = resolve; }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ success: true, obj: 'fresh-csrf' })))
    .mockResolvedValueOnce(new Response(null, { status: 401 }));
  vi.stubGlobal('fetch', fetchMock);
  render(<MiniAppEntry />);
  await act(async () => { await vi.advanceTimersByTimeAsync(15_000); });
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: '重试' })); });
  expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(['/csrf-token', '/csrf-token', '/tg-miniapp/auth']);
  expect(fetchMock.mock.calls[2]?.[1].headers).toMatchObject({ 'X-CSRF-Token': 'fresh-csrf' });
  await act(async () => {
    finishFirst(new Response(JSON.stringify({ success: true, obj: 'late-csrf' })));
  });
  expect(fetchMock).toHaveBeenCalledTimes(3);
  expect(screen.queryByRole('button', { name: '重试' })).toBeNull();
  expect(screen.getByText(/授权已过期/)).toBeTruthy();
});

test('a stalled Mini App authentication request ends with recoverable feedback', async () => {
  vi.useFakeTimers();
  window.Telegram = { WebApp: { initData: 'synthetic-fixture' } };
  const fetchMock = vi.fn((_url: string, options: RequestInit) =>
    new Promise<Response>((_resolve, reject) => {
      options.signal?.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
    }),
  );
  vi.stubGlobal('fetch', fetchMock);
  render(<MiniAppEntry />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(15_000);
  });
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock.mock.calls[0]?.[1].signal?.aborted).toBe(true);
  expect(screen.getByText(/请从 Telegram 机器人重新打开小程序/).getAttribute('aria-live')).toBe('polite');
});
