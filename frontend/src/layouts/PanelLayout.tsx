import { Outlet } from 'react-router';

import { useWebSocketBridge } from '@/api/websocketBridge';
import { usePageTitle } from '@/hooks/usePageTitle';
import CommandPalette from '@/components/command-palette/CommandPalette';
import MiniAppBottomNav from '@/components/miniapp/MiniAppBottomNav';

export default function PanelLayout() {
  useWebSocketBridge();
  usePageTitle();
  return (
    <>
      <Outlet />
      <CommandPalette />
      <MiniAppBottomNav />
    </>
  );
}
