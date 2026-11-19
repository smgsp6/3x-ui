import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { afterEach, expect, test, vi } from 'vitest';
import SettingsPage from '@/pages/settings/SettingsPage';
import { HttpUtil, Msg, PromiseUtil } from '@/utils';
import { renderWithProviders } from './test-utils';

const settings = vi.hoisted(() => ({ fetched: false, saveDisabled: false }));
vi.mock('@/layouts/AppSidebar', () => ({ default: () => null }));
vi.mock('@/pages/settings/GeneralTab', () => ({ default: () => null }));
vi.mock('@/api/queries/useAllSettings', () => ({
  useAllSettings: () => ({ allSetting: { webBasePath: '/beta/' }, spinning: false, setSpinning: () => {}, ...settings }),
}));

afterEach(() => { delete window.X_UI_TG_MINIAPP_MODE; });

test('Mini App settings keep a draft when leaving is canceled', async () => {
  window.X_UI_TG_MINIAPP_MODE = true;
  const router = createMemoryRouter([
    { path: '/settings', element: <SettingsPage /> },
    { path: '/clients', element: <div>Client destination</div> },
  ], { initialEntries: ['/settings'] });
  renderWithProviders(<RouterProvider router={router} />);
  await act(async () => { await router.navigate('/settings#security'); });
  expect(router.state.location.hash).toBe('#security');

  await act(async () => { await router.navigate('/clients'); });
  expect(router.state.location.pathname).toBe('/settings');
  expect(await screen.findByText('设置尚未保存')).toBeTruthy();
  fireEvent.keyDown(await screen.findByRole('dialog'), { key: 'Escape', keyCode: 27 });
  await waitFor(() => expect([...router.state.blockers.values()].every((blocker) =>
    blocker.state === 'unblocked')).toBe(true));
  expect(router.state.location.pathname).toBe('/settings');

  await act(async () => { await router.navigate('/clients'); });
  fireEvent.click(await screen.findByRole('button', { name: '放弃并离开' }));
  expect(await screen.findByText('Client destination')).toBeTruthy();
});

test('Mini App settings restart returns through the same HTTPS reverse proxy', async () => {
  window.X_UI_TG_MINIAPP_MODE = true;
  settings.fetched = true;
  settings.saveDisabled = true;
  const originalLocation = Object.getOwnPropertyDescriptor(window, 'location')!;
  const replace = vi.fn();
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: {
      href: 'https://synthetic.invalid:8443/panel/settings', hostname: 'synthetic.invalid',
      pathname: '/panel/settings', port: '8443', protocol: 'https:', replace },
  });
  const sleep = vi.spyOn(PromiseUtil, 'sleep').mockResolvedValue();
  vi.mocked(HttpUtil.post).mockResolvedValueOnce(new Msg(true));
  try {
    const router = createMemoryRouter([{ path: '/settings', element: <SettingsPage /> }], {
      initialEntries: ['/settings'],
    });
    const view = renderWithProviders(<RouterProvider router={router} />);
    fireEvent.click(screen.getByRole('button', { name: 'Restart Panel' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Restart Panel' }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith('https://synthetic.invalid:8443/beta/panel/settings'));
    view.unmount();
  } finally {
    sleep.mockRestore();
    Object.defineProperty(window, 'location', originalLocation);
    settings.fetched = false;
    settings.saveDisabled = false;
  }
});
