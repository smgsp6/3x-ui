import { act, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { expect, test, vi } from 'vitest';
import CertificatesPage from '@/pages/certificates/CertificatesPage';
import { HttpUtil, Msg } from '@/utils';

vi.mock('@/layouts/AppSidebar', () => ({ default: () => null }));

test('late certificate status cannot overwrite the current request', async () => {
  const finish: ((response: Msg) => void)[] = [];
  const get = vi.spyOn(HttpUtil, 'get').mockImplementation(() => new Promise((resolve) => finish.push(resolve)));
  try {
    const view = render(<MemoryRouter><CertificatesPage /></MemoryRouter>, { reactStrictMode: true });
    expect(finish).toHaveLength(2);
    expect(get.mock.calls[0]?.[2]?.signal?.aborted).toBe(true);
    expect(screen.queryByText('Telegram 到期提醒尚未启用')).toBeNull();

    await act(async () => finish[1]!(new Msg(true, '', { certificates: [], alertsEnabled: true })));
    await act(async () => finish[0]!(new Msg(true, '', { certificates: [], alertsEnabled: false })));
    expect(screen.getByText('Telegram 到期提醒已启用')).toBeTruthy();
    expect(screen.queryByText('Telegram 到期提醒尚未启用')).toBeNull();
    view.unmount();
  } finally {
    get.mockRestore();
  }
});

test('certificate diagnostics describe configured files and how to verify the served chain', async () => {
  const get = vi.spyOn(HttpUtil, 'get').mockResolvedValue(new Msg(true, '', {
    certificates: [{ purpose: 'panel', dnsNames: ['panel.example.test'], status: 'valid', daysRemaining: 45 }],
    alertsEnabled: true,
  }));
  try {
    render(<MemoryRouter><CertificatesPage /></MemoryRouter>);
    expect(await screen.findByText('证书文件检查通过')).toBeTruthy();
    expect(screen.getByText(/核对服务实际呈现的证书链/)).toBeTruthy();
    expect(screen.getByText(/检查管理面板和订阅服务配置的证书文件/)).toBeTruthy();
  } finally {
    get.mockRestore();
  }
});
