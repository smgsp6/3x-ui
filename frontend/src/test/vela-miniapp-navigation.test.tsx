import { fireEvent, screen, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router';
import { afterEach, expect, test } from 'vitest';

import MiniAppBottomNav from '@/components/miniapp/MiniAppBottomNav';
import { PANEL_ROUTES } from '@/routes/panelRoutes';
import { renderWithProviders } from './test-utils';

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
});

test('original panel hides the Telegram-only bottom navigation', () => {
  window.X_UI_TG_MINIAPP_MODE = false;
  renderNav();
  expect(screen.queryByRole('navigation', { name: 'Vela 小程序主导航' })).toBeNull();
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

test('advanced Xray functions remain in the More drawer', () => {
  window.X_UI_TG_MINIAPP_MODE = true;
  renderNav();
  const nav = screen.getByRole('navigation', { name: 'Vela 小程序主导航' });
  fireEvent.click(within(nav).getByRole('button', { name: '更多' }));
  const advanced = PANEL_ROUTES.filter((r) => !['/', '/nodes', '/clients', '/certificates'].includes(r.path));
  const entries = document.querySelectorAll<HTMLButtonElement>('.vela-more-entry');
  expect(entries.length).toBe(advanced.length);
  const inboundIndex = advanced.findIndex((r) => r.path === '/inbounds');
  expect(inboundIndex).toBeGreaterThanOrEqual(0);
  expect(advanced.some((r) => r.path === '/routing')).toBe(true);
  expect(advanced.some((r) => r.path === '/xray')).toBe(true);
  fireEvent.click(entries[inboundIndex]!);
  expect(screen.getByTestId('current-route').textContent).toBe('/inbounds');
});
