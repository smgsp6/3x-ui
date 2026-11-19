import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';
import { Drawer } from 'antd';
import {
  AppstoreOutlined,
  CloudServerOutlined,
  HomeOutlined,
  LogoutOutlined,
  SafetyCertificateOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import { PANEL_ROUTES } from '@/routes/panelRoutes';
import { leaveMiniAppSession } from '@/api/http-init';
import { HttpUtil } from '@/utils';
import './MiniAppBottomNav.css';

declare global {
  interface Window {
    X_UI_TG_MINIAPP_MODE?: boolean;
  }
}

const primary = [
  { path: '/', name: '首页', Icon: HomeOutlined },
  { path: '/nodes', name: '服务器', Icon: CloudServerOutlined },
  { path: '/clients', name: '客户端', Icon: TeamOutlined },
  { path: '/certificates', name: '证书', Icon: SafetyCertificateOutlined },
];

const editableSelector = 'textarea:not([readonly]):not([disabled]), input:not([readonly]):not([disabled]):is([type="text"], [type="search"], [type="email"], [type="password"], [type="tel"], [type="url"], [type="number"], :not([type])), [contenteditable]:not([contenteditable="false"])';

function dismissPageDialog(): boolean {
  const dialogs = document.querySelectorAll<HTMLElement>('[role="dialog"][aria-modal="true"]');
  for (const dialog of Array.from(dialogs).reverse()) {
    if (dialog.closest('.vela-more-drawer, [hidden], [aria-hidden="true"], .ant-drawer-content-wrapper-hidden')) continue;
    const wrapper = dialog.closest<HTMLElement>('.ant-modal-wrap') ?? dialog;
    if (window.getComputedStyle(wrapper).display === 'none') continue;
    // Use the dialog's own close action so its cancel and draft logic still run.
    dialog.querySelector<HTMLButtonElement>('.ant-modal-close:not(:disabled), .ant-drawer-close:not(:disabled)')?.click();
    return true;
  }
  return false;
}

/** All advanced Xray settings remain reachable; do not hide features on mobile. */
export default function MiniAppBottomNav() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [moreOpen, setMoreOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [keyboardOpen, setKeyboardOpen] = useState(false);
  const moreSelected = !primary.some((item) => item.path === pathname);
  const allRoutes = useMemo(
    () => PANEL_ROUTES.filter((route) => !primary.some((p) => p.path === route.path)),
    [],
  );

  useEffect(() => {
    const viewport = window.visualViewport;
    if (!window.X_UI_TG_MINIAPP_MODE || !viewport) return;
    const update = () => {
      const editable = document.activeElement?.closest(editableSelector);
      setKeyboardOpen(Boolean(editable && viewport.scale === 1 && window.innerHeight - viewport.height > 120));
    };
    // focusout can run before activeElement is updated.
    let frame = 0;
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(update);
    };
    viewport.addEventListener('resize', schedule);
    document.addEventListener('focusin', schedule);
    document.addEventListener('focusout', schedule);
    schedule();
    return () => {
      cancelAnimationFrame(frame);
      viewport.removeEventListener('resize', schedule);
      document.removeEventListener('focusin', schedule);
      document.removeEventListener('focusout', schedule);
    };
  }, []);

  // The official Telegram WebApp BackButton is a separate control from
  // browser history. Never navigate(-1): a Mini App may open as a deep link
  // with no same-origin previous entry. Close the app drawer first, then
  // dismiss a page dialog, or return to the safe dashboard root.
  useEffect(() => {
    if (!window.X_UI_TG_MINIAPP_MODE) return;
    const backButton = window.Telegram?.WebApp?.BackButton;
    if (!backButton?.onClick || !backButton.offClick) return;
    const shouldShow = moreOpen || pathname !== '/';
    if (!shouldShow) {
      backButton.hide();
      return;
    }
    const handleBack = () => {
      if (moreOpen) setMoreOpen(false);
      else if (!dismissPageDialog()) navigate('/');
    };
    backButton.onClick(handleBack);
    backButton.show();
    return () => {
      backButton.offClick(handleBack);
      backButton.hide();
    };
  }, [moreOpen, navigate, pathname]);

  if (!window.X_UI_TG_MINIAPP_MODE) return null;
  const logout = async () => {
    setSigningOut(true);
    try {
      const result = await HttpUtil.post('/logout', undefined, { timeout: 15_000 });
      if (result.success) leaveMiniAppSession();
    } finally {
      setSigningOut(false);
    }
  };
  return (
    <>
      <nav className="tg-app-bottom-nav" aria-label="Vela 小程序主导航" data-keyboard-open={keyboardOpen || undefined}>
        {primary.map(({ path, name, Icon }) => (
          <button
            key={path}
            type="button"
            className={pathname === path ? 'tg-bottom-item active' : 'tg-bottom-item'}
            aria-current={pathname === path ? 'page' : undefined}
            onClick={() => navigate(path)}
          >
            <Icon aria-hidden />
            <span>{name}</span>
          </button>
        ))}
        <button
          type="button"
          className={moreSelected || moreOpen ? 'tg-bottom-item active' : 'tg-bottom-item'}
          aria-expanded={moreOpen}
          aria-controls="vela-more-drawer"
          onClick={() => setMoreOpen(true)}
        >
          <AppstoreOutlined aria-hidden />
          <span>更多</span>
        </button>
      </nav>
      <Drawer
        placement="bottom"
        size="min(75dvh, 620px)"
        open={moreOpen}
        onClose={() => setMoreOpen(false)}
        title="Vela · 全部功能"
        rootClassName="vela-more-drawer"
        styles={{ body: { padding: 18 } }}
      >
        <div className="vela-more-grid" id="vela-more-drawer">
          {allRoutes.map((route) => {
            const Icon = route.icon;
            return (
              <button
                type="button"
                className="vela-more-entry"
                key={route.path}
                onClick={() => { setMoreOpen(false); navigate(route.path); }}
              >
                <span className="vela-more-entry-icon"><Icon aria-hidden /></span>
                <span>{t(route.titleKey)}</span>
              </button>
            );
          })}
          <button type="button" className="vela-more-entry" disabled={signingOut} onClick={() => void logout()}>
            <span className="vela-more-entry-icon"><LogoutOutlined aria-hidden /></span>
            <span>{t('logout')}</span>
          </button>
        </div>
      </Drawer>
    </>
  );
}
