import { leaveMiniAppSession } from '@/api/http-init';
import { HttpUtil } from '@/utils';

let pendingLogout: Promise<void> | undefined;

export function logoutMiniApp(): Promise<void> {
  pendingLogout ??= (async () => {
    const result = await HttpUtil.post('/logout', undefined, { timeout: 15_000 });
    if (result.success) {
      leaveMiniAppSession();
      return;
    }

    // The server may have revoked the session before the response was lost.
    // A read-only request lets the shared 401 handler retire the current page.
    await HttpUtil.get('/panel/api/tg-miniapp/status', undefined, { silent: true, timeout: 5_000 });
  })().finally(() => { pendingLogout = undefined; });
  return pendingLogout;
}
