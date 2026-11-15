import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { SafetyCertificateOutlined, LoadingOutlined } from '@ant-design/icons';
import './miniapp.css';
import velaIcon from '@/assets/vela-mark.png';

type TelegramApp = {
  initData: string;
  ready?: () => void;
  expand?: () => void;
  BackButton?: {
    show: () => void;
    hide: () => void;
    onClick: (callback: () => void) => void;
    offClick: (callback: () => void) => void;
  };
};

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramApp };
  }
}

function MiniAppEntry() {
  const [error, setError] = useState('');
  const [state, setState] = useState('正在验证 Telegram 身份…');

  useEffect(() => {
    let canceled = false;
    void (async () => {
      const app = window.Telegram?.WebApp;
      app?.ready?.();
      app?.expand?.();
      const initData = app?.initData;
      if (!initData) {
        if (!canceled) setError('请通过 Telegram 机器人内的「打开管理面板」按钮进入。');
        return;
      }
      const base = window.X_UI_BASE_PATH || '/';
      try {
        let csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
        if (!csrf) {
          const tokenResponse = await fetch(`${base}csrf-token`, { credentials: 'same-origin', cache: 'no-store' });
          if (!tokenResponse.ok) throw new Error('csrf');
          const tokenData = (await tokenResponse.json()) as { success?: boolean; obj?: string };
          if (!tokenData.success || !tokenData.obj) throw new Error('csrf');
          csrf = tokenData.obj;
        }
        if (!canceled) setState('正在建立安全会话…');
        const response = await fetch(`${base}tg-miniapp/auth`, {
          method: 'POST',
          credentials: 'same-origin',
          cache: 'no-store',
          headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
          body: JSON.stringify({ initData }),
        });
        if (!response.ok) throw new Error('auth');
        const outcome = (await response.json()) as { success?: boolean };
        if (!outcome.success) throw new Error('auth');
        if (!canceled) window.location.replace(`${base}panel/`);
      } catch {
        if (!canceled) setError('验证失败或授权已过期。请从 Telegram 机器人重新打开小程序。');
      }
    })();
    return () => { canceled = true; };
  }, []);

  return (
    <main className="tg-welcome-shell">
      <div className="tg-welcome-glow" />
      <div className="tg-welcome-card">
        <div className="tg-welcome-mark"><img src={velaIcon} alt="Vela 标志" width="80" height="80" /></div>
        <div className="tg-welcome-eyebrow">VELA · SECURE CONTROL</div>
        <h1>Vela</h1>
        <p className="tg-welcome-description">你的云端舰队控制中心 · Telegram Mini App</p>
        <div className="tg-welcome-progress">
          <span className="tg-welcome-icon">{error ? <SafetyCertificateOutlined /> : <LoadingOutlined spin />}</span>
          <span aria-live="polite">{error || state}</span>
        </div>
        <div className="tg-welcome-note">HTTPS 传输 · 服务端验证身份 · 私密数据保留在你的服务器</div>
      </div>
    </main>
  );
}

const root = document.getElementById('app');
if (root) createRoot(root).render(<MiniAppEntry />);
