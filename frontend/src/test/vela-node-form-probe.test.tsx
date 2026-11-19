import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import NodeFormModal from '@/pages/nodes/NodeFormModal';
import type { ProbeResult } from '@/schemas/node';
import { Msg } from '@/utils';
import { renderWithProviders } from './test-utils';

vi.mock('@/api/queries/useOutboundTags', () => ({ useOutboundTagGroups: () => ({}) }));

test('a delayed certificate fingerprint does not replace the pin for a changed node address', async () => {
  let finish!: (result: Msg<string>) => void;
  const fetchFingerprint = vi.fn(() => new Promise<Msg<string>>((resolve) => { finish = resolve; }));
  const oldPin = '1'.repeat(64);
  const latePin = '2'.repeat(64);
  renderWithProviders(<NodeFormModal
    open
    mode="edit"
    node={{ id: 1, name: 'Fixture', address: 'old.example.test', tlsVerifyMode: 'pin', pinnedCertSha256: oldPin }}
    testConnection={vi.fn()}
    fetchFingerprint={fetchFingerprint}
    fetchInbounds={vi.fn()}
    save={vi.fn()}
    onOpenChange={vi.fn()}
  />);
  fireEvent.click(screen.getByRole('button', { name: 'Fetch' }));
  await waitFor(() => expect(fetchFingerprint).toHaveBeenCalledTimes(1));
  fireEvent.change(screen.getByRole('textbox', { name: 'Address' }), { target: { value: 'new.example.test' } });
  await act(async () => finish(new Msg(true, '', latePin)));
  expect(screen.getByDisplayValue(oldPin)).toBeTruthy();
  expect(screen.queryByDisplayValue(latePin)).toBeNull();
});

test('leaving the node page during a save probe does not submit a stale draft', async () => {
  let finish!: (result: Msg<ProbeResult>) => void;
  const testConnection = vi.fn(() => new Promise<Msg<ProbeResult>>((resolve) => { finish = resolve; }));
  const save = vi.fn();
  const view = renderWithProviders(<NodeFormModal
    open
    mode="edit"
    node={{ id: 1, name: 'Fixture', address: 'node.example.test', hasApiToken: true }}
    testConnection={testConnection}
    fetchFingerprint={vi.fn()}
    fetchInbounds={vi.fn()}
    save={save}
    onOpenChange={vi.fn()}
  />);
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(testConnection).toHaveBeenCalledTimes(1));
  view.unmount();
  await act(async () => finish(new Msg(true, '', { status: 'online' })));
  expect(save).not.toHaveBeenCalled();
});
