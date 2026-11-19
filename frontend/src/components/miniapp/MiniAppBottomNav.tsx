import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';
import { Drawer, Modal } from 'antd';
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

function activeKeyboardField(): HTMLElement | null {
  const field = document.activeElement?.closest<HTMLElement>(editableSelector);
  const viewport = window.visualViewport;
  return field && viewport?.scale === 1 && window.innerHeight - viewport.height > 120 ? field : null;
}

function topPageDialog(moreOpen: boolean) {
  let top: { dialog: HTMLElement; layer: number } | undefined;
  const dialogs = document.querySelectorAll<HTMLElement>('[role="dialog"][aria-modal="true"]');
  for (const dialog of dialogs) {
    if (dialog.classList.contains('vela-editor-discard') ||
      (!moreOpen && dialog.closest('.vela-more-drawer'))) continue;
    if (dialog.closest('[hidden], [aria-hidden="true"], .ant-drawer-content-wrapper-hidden')) continue;
    const wrapper = dialog.closest<HTMLElement>('.ant-modal-wrap, .ant-drawer') ?? dialog;
    const style = window.getComputedStyle(wrapper);
    if (style.display === 'none' || style.visibility === 'hidden') continue;
    const layer = Number.parseInt(style.zIndex, 10) || 1000;
    if (!top || layer >= top.layer) top = { dialog, layer };
  }
  return top;
}

/** All advanced Xray settings remain reachable; do not hide features on mobile. */
export default function MiniAppBottomNav() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [moreOpen, setMoreOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [keyboardOpen, setKeyboardOpen] = useState(false);
  const [discard, setDiscard] = useState<{ close: HTMLButtonElement; layer: number } | null>(null);
  const moreSelected = !primary.some((item) => item.path === pathname);
  const allRoutes = useMemo(
    () => PANEL_ROUTES.filter((route) => !primary.some((p) => p.path === route.path)),
    [],
  );

  useEffect(() => {
    const viewport = window.visualViewport;
    if (!window.X_UI_TG_MINIAPP_MODE || !viewport) return;
    const update = () => {
      setKeyboardOpen(Boolean(activeKeyboardField()));
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

  useEffect(() => {
    if (!window.X_UI_TG_MINIAPP_MODE) return;
    const backButton = window.Telegram?.WebApp?.BackButton;
    if (!backButton?.onClick || !backButton.offClick) return;

    const handleBack = () => {
      const field = activeKeyboardField();
      if (field) {
        field.blur();
        return;
      }
      if (discard) {
        setDiscard(null);
        return;
      }
      const top = topPageDialog(moreOpen);
      if (top) {
        const close = top.dialog.querySelector<HTMLButtonElement>('.ant-modal-close:not(:disabled), .ant-drawer-close:not(:disabled)');
        if (close && close.closest('[role="dialog"]') === top.dialog) {
          if (top.dialog.classList.contains('vela-confirm-editor-close')) {
            setDiscard({ close, layer: top.layer + 1 });
          } else {
            close.click();
          }
        }
        return;
      }
      if (moreOpen) setMoreOpen(false);
      else if (pathname !== '/') navigate('/');
    };

    let registered: boolean | undefined;
    const update = () => {
      const visible = pathname !== '/' || moreOpen || keyboardOpen || Boolean(discard || topPageDialog(moreOpen));
      if (visible === registered) return;
      if (visible) {
        backButton.onClick(handleBack);
        backButton.show();
      } else {
        if (registered) backButton.offClick(handleBack);
        backButton.hide();
      }
      registered = visible;
    };
    let frame = 0;
    const observer = pathname === '/' && new MutationObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(update);
    });
    if (observer) observer.observe(document.body, {
      subtree: true, childList: true, attributes: true,
      attributeFilter: ['class', 'style', 'hidden', 'aria-hidden'],
    });
    update();
    return () => {
      if (observer) observer.disconnect();
      cancelAnimationFrame(frame);
      if (registered) backButton.offClick(handleBack);
      backButton.hide();
    };
  }, [discard, keyboardOpen, moreOpen, navigate, pathname]);

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
      <Modal
        open={Boolean(discard)}
        title="关闭编辑？"
        className="vela-editor-discard"
        zIndex={discard?.layer}
        okText="关闭并放弃修改"
        okButtonProps={{ danger: true }}
        cancelText="继续编辑"
        onCancel={() => setDiscard(null)}
        onOk={() => {
          if (discard?.close.isConnected) discard.close.click();
          setDiscard(null);
        }}
      >
        未保存的修改可能丢失。
      </Modal>
      <Drawer
        placement="bottom"
        size="min(75dvh, 620px)"
        open={moreOpen}
        onClose={() => setMoreOpen(false)}
        title="Vela · 全部功能"
        rootClassName="vela-more-drawer"
        styles={{ body: { paddingTop: 18 } }}
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
