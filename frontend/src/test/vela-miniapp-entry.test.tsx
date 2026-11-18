import { act, render, screen } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { MiniAppEntry } from '@/entries/miniapp';

afterEach(() => {
  delete window.Telegram;
  vi.unstubAllGlobals();
  vi.useRealTimers();
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
