import { useLayoutEffect, useRef, useState } from 'react';
import { Button, Input, Modal } from 'antd';
import { MemoryRouter, useLocation } from 'react-router';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, waitFor, within } from 'storybook/test';

import MiniAppBottomNav from './MiniAppBottomNav';

function ClientEditor() {
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  return (
    <>
      <output aria-label="Current page">{pathname}</output>
      <Button onClick={() => setOpen(true)}>Edit client</Button>
      <Modal title="Edit client" open={open} onCancel={() => setOpen(false)}>
        <Input aria-label="Client name" value={name} onChange={(event) => setName(event.target.value)} />
      </Modal>
    </>
  );
}

function TelegramNavigation() {
  const pressBack = useRef<(() => void) | null>(null);
  const [ready, setReady] = useState(false);
  useLayoutEffect(() => {
    const previousTelegram = window.Telegram;
    const previousMode = window.X_UI_TG_MINIAPP_MODE;
    window.X_UI_TG_MINIAPP_MODE = true;
    window.Telegram = { WebApp: {
      initData: '',
      BackButton: {
        show() {},
        hide() {},
        onClick(callback) { pressBack.current = callback; },
        offClick(callback) {
          if (pressBack.current === callback) pressBack.current = null;
        },
      },
    } };
    setReady(true);
    return () => {
      window.Telegram = previousTelegram;
      window.X_UI_TG_MINIAPP_MODE = previousMode;
    };
  }, []);

  return ready && (
    <MemoryRouter initialEntries={['/clients']}>
      <Button onClick={() => pressBack.current?.()}>Telegram Back</Button>
      <ClientEditor />
      <MiniAppBottomNav />
    </MemoryRouter>
  );
}

const meta = { title: 'Vela/Mini App Navigation', component: TelegramNavigation } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

export const BackFromClientEditor: Story = {
  play: async ({ canvas, canvasElement, userEvent }) => {
    const editor = canvas.getByRole('button', { name: 'Edit client' });
    const back = canvas.getByRole('button', { name: 'Telegram Back' });
    const page = within(canvasElement.ownerDocument.body);
    await userEvent.click(editor);
    const dialog = await page.findByRole('dialog', { name: 'Edit client' });
    await userEvent.type(within(dialog).getByRole('textbox', { name: 'Client name' }), 'Synthetic client');
    // Trigger the host bridge outside the web page's modal focus trap.
    back.click();
    await waitFor(() => expect(page.queryByRole('dialog', { name: 'Edit client' })).toBeNull());
    await expect(canvas.getByLabelText('Current page')).toHaveTextContent('/clients');
    await userEvent.click(editor);
    const current = await page.findByRole('dialog', { name: 'Edit client' });
    await expect(within(current).getByRole('textbox', { name: 'Client name' })).toHaveValue('Synthetic client');
    back.click();
    await waitFor(() => expect(page.queryByRole('dialog', { name: 'Edit client' })).toBeNull());
    await userEvent.click(back);
    await expect(canvas.getByLabelText('Current page')).toHaveTextContent(/^\/$/);
  },
};
