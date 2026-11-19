import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { Modal } from 'antd';
import { useState } from 'react';
import { MemoryRouter, useLocation } from 'react-router';
import { afterEach, expect, test, vi } from 'vitest';

import MiniAppBottomNav from '@/components/miniapp/MiniAppBottomNav';
import { PANEL_ROUTES } from '@/routes/panelRoutes';
import { HttpUtil, Msg } from '@/utils';
import { leaveMiniAppSession } from '@/api/http-init';
import { renderWithProviders } from './test-utils';

vi.mock('@/api/http-init', { spy: true });

function CurrentPath() {
  const location = useLocation();
  return <output data-testid="current-route">{location.pathname}</output>;
}

function renderNav(initialPath = '/') {
  return renderWithProviders(
    <MemoryRouter initialEntries={[initialPath]}>
      <MiniAppBottomNav />
      <CurrentPath />
    </MemoryRouter>,
  );
}

afterEach(() => {
  window.X_UI_TG_MINIAPP_MODE = undefined;
  window.Telegram = undefined;
});

test('original panel hides the Telegram-only bottom navigation', () => {
  window.X_UI_TG_MINIAPP_MODE = false;
  renderNav();
  expect(screen.queryByRole('navigation', { name: 'Vela 小程序主导航' })).toBeNull();
});

test('Mini App navigation yields to a reduced editing viewport and returns after blur', async () => {
  window.X_UI_TG_MINIAPP_MODE = true;
  const viewport = Object.assign(new EventTarget(), { height: window.innerHeight, scale: 1 });
  vi.stubGlobal('visualViewport', viewport);
  try {
    const view = renderNav();
    const nav = screen.getByRole('navigation', { name: 'Vela 小程序主导航' });
    const input = document.createElement('input');
    view.container.append(input);
    input.focus();
    viewport.height = window.innerHeight - 300;
    viewport.dispatchEvent(new Event('resize'));
    await waitFor(() => expect(nav.getAttribute('data-keyboard-open')).toBe('true'));
    input.blur();
    await waitFor(() => expect(nav.hasAttribute('data-keyboard-open')).toBe(false));
    view.unmount();
  } finally {
    vi.unstubAllGlobals();
  }
});

test('Telegram navigation uses actual panel routes', () => {
  window.X_UI_TG_MINIAPP_MODE = true;
  renderNav();
  const nav = screen.getByRole('navigation', { name: 'Vela 小程序主导航' });
  expect(within(nav).getAllByRole('button')).toHaveLength(5);
  fireEvent.click(within(nav).getByRole('button', { name: '客户端' }));
  expect(screen.getByTestId('current-route').textContent).toBe('/clients');
  fireEvent.click(within(nav).getByRole('button', { name: '证书' }));
  expect(screen.getByTestId('current-route').textContent).toBe('/certificates');
});

test('advanced Xray functions remain in the More drawer', async () => {
  window.X_UI_TG_MINIAPP_MODE = true;
  renderNav();
  const nav = screen.getByRole('navigation', { name: 'Vela 小程序主导航' });
  fireEvent.click(within(nav).getByRole('button', { name: '更多' }));
  const advanced = PANEL_ROUTES.filter((r) => !['/', '/nodes', '/clients', '/certificates'].includes(r.path));
  await waitFor(() => {
    expect(document.querySelectorAll('.vela-more-entry')).toHaveLength(advanced.length + 1);
  });
  const entries = document.querySelectorAll<HTMLButtonElement>('.vela-more-entry');
  const inboundIndex = advanced.findIndex((r) => r.path === '/inbounds');
  expect(inboundIndex).toBeGreaterThanOrEqual(0);
  expect(advanced.some((r) => r.path === '/routing')).toBe(true);
  expect(advanced.some((r) => r.path === '/xray')).toBe(true);
  fireEvent.click(entries[inboundIndex]!);
  expect(screen.getByTestId('current-route').textContent).toBe('/inbounds');
});

test('mobile logout waits for server success before leaving the session', async () => {
  window.X_UI_TG_MINIAPP_MODE = true;
  vi.mocked(leaveMiniAppSession).mockImplementation(() => {});
  const post = vi.mocked(HttpUtil.post);
  let failLogout!: (result: Msg) => void;
  post
    .mockImplementationOnce(() => new Promise((resolve) => { failLogout = resolve; }))
    .mockResolvedValueOnce(new Msg(true));
  renderNav();
  fireEvent.click(screen.getByRole('button', { name: '更多' }));
  const entries = document.querySelectorAll<HTMLButtonElement>('.vela-more-entry');
  const logout = entries[entries.length - 1]!;
  fireEvent.click(logout);
  expect(logout.disabled).toBe(true);
  fireEvent.click(logout);
  expect(post).toHaveBeenCalledTimes(1);
  failLogout(new Msg(false));
  await waitFor(() => expect(logout.disabled).toBe(false));
  expect(leaveMiniAppSession).not.toHaveBeenCalled();
  fireEvent.click(logout);
  await waitFor(() => expect(leaveMiniAppSession).toHaveBeenCalledTimes(1));
  expect(post).toHaveBeenLastCalledWith('/logout', undefined, { timeout: 15_000 });
});

test('Telegram native BackButton closes More first then returns safely to dashboard', async () => {
  const callbacks = new Set<() => void>();
  const back = {
    show: vi.fn(),
    hide: vi.fn(),
    onClick: vi.fn((cb: () => void) => { callbacks.add(cb); }),
    offClick: vi.fn((cb: () => void) => { callbacks.delete(cb); }),
  };
  window.Telegram = { WebApp: { initData: '', BackButton: back } };
  window.X_UI_TG_MINIAPP_MODE = true;
  const rendered = renderNav('/clients');

  await waitFor(() => {
    expect(back.show).toHaveBeenCalled();
    expect(callbacks.size).toBe(1);
  });
  // Native back from a deep link must return to the panel dashboard,
  // not escape the Telegram WebView through browser history.
  fireEvent.click(screen.getByRole('button', { name: '更多' }));
  await waitFor(() => { expect(callbacks.size).toBe(1); });
  const backWhileDrawer = [...callbacks][0]!;
  act(backWhileDrawer);
  await waitFor(() => {
    expect(screen.getByRole('button', { name: '更多' }).getAttribute('aria-expanded')).toBe('false');
    expect(screen.getByTestId('current-route').textContent).toBe('/clients');
    expect(callbacks.size).toBe(1);
  });
  act([...callbacks][0]!);
  await waitFor(() => {
    expect(screen.getByTestId('current-route').textContent).toBe('/');
    expect(callbacks.size).toBe(0);
    expect(back.hide).toHaveBeenCalled();
  });
  rendered.unmount();
  expect(callbacks.size).toBe(0);
  expect(back.offClick).toHaveBeenCalled();
});

test('Telegram native BackButton lets an open edit dialog handle cancellation first', async () => {
  let clickBack: (() => void) | undefined;
  window.Telegram = { WebApp: { initData: '', BackButton: {
    show: vi.fn(),
    hide: vi.fn(),
    onClick: (callback) => { clickBack = callback; },
    offClick: () => { clickBack = undefined; },
  } } };
  window.X_UI_TG_MINIAPP_MODE = true;

  function EditDialog() {
    const [open, setOpen] = useState(true);
    return open ? <Modal open title="Edit synthetic client" onCancel={() => setOpen(false)} /> : null;
  }
  renderWithProviders(
    <MemoryRouter initialEntries={['/clients']}>
      <MiniAppBottomNav />
      <CurrentPath />
      <EditDialog />
    </MemoryRouter>,
  );

  expect(screen.getByRole('dialog', { name: 'Edit synthetic client' })).toBeTruthy();
  act(() => clickBack?.());
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect(screen.getByTestId('current-route').textContent).toBe('/clients');
  act(() => clickBack?.());
  expect(screen.getByTestId('current-route').textContent).toBe('/');
});

test('missing Telegram WebApp bridge does not block regular Mini App navigation', () => {
  window.X_UI_TG_MINIAPP_MODE = true;
  window.Telegram = undefined;
  renderNav('/clients');
  fireEvent.click(screen.getByRole('button', { name: '证书' }));
  expect(screen.getByTestId('current-route').textContent).toBe('/certificates');
});

test('native Back dismisses the keyboard, respects the highest locked dialog, and protects editor changes', async () => {
  let clickBack: (() => void) | undefined;
  window.Telegram = { WebApp: { initData: '', BackButton: {
    show: vi.fn(), hide: vi.fn(),
    onClick: (callback) => { clickBack = callback; },
    offClick: () => { clickBack = undefined; },
  } } };
  window.X_UI_TG_MINIAPP_MODE = true;
  const viewport = Object.assign(new EventTarget(), { height: window.innerHeight, scale: 1 });
  vi.stubGlobal('visualViewport', viewport);
  const close = vi.fn();
  try {
    const renderDialogs = (locked: boolean) => (
      <MemoryRouter initialEntries={['/clients']}>
        <MiniAppBottomNav />
        <CurrentPath />
        {locked && <Modal open zIndex={1300} closable={false} title="Locked operation" />}
        <Modal open zIndex={1100} className="vela-confirm-editor-close" title="Editor" onCancel={close}>
          <input defaultValue="Unsaved synthetic draft" aria-label="Draft" />
        </Modal>
      </MemoryRouter>
    );
    const view = renderWithProviders(renderDialogs(true));
    act(() => clickBack?.());
    expect(close).not.toHaveBeenCalled();
    expect(screen.queryByText('关闭编辑？')).toBeNull();
    expect(screen.getByTestId('current-route').textContent).toBe('/clients');
    view.rerender(renderDialogs(false));

    const input = screen.getByRole('textbox', { name: 'Draft' });
    act(() => input.focus());
    viewport.height = window.innerHeight - 270;
    act(() => clickBack?.());
    expect(document.activeElement).not.toBe(input);
    expect(screen.queryByText('关闭编辑？')).toBeNull();

    act(() => clickBack?.());
    expect(await screen.findByText('关闭编辑？')).toBeTruthy();
    act(() => clickBack?.());
    expect(close).not.toHaveBeenCalled();
    expect((input as HTMLInputElement).value).toBe('Unsaved synthetic draft');

    act(() => clickBack?.());
    fireEvent.click(await screen.findByRole('button', { name: '关闭并放弃修改' }));
    expect(close).toHaveBeenCalledOnce();
  } finally {
    vi.unstubAllGlobals();
  }
});
