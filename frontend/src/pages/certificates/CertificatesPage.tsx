import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { Alert, Button, Layout, Spin, Tag } from 'antd';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { HttpUtil } from '@/utils';
import AppSidebar from '@/layouts/AppSidebar';
import './CertificatesPage.css';

type CertState = 'valid' | 'expiring' | 'expired' | 'invalid' | 'unconfigured';
type Certificate = {
  purpose: string;
  dnsNames: string[];
  issuer?: string;
  validFrom?: string;
  validUntil?: string;
  daysRemaining: number;
  status: CertState;
};
const stateNames: Record<CertState, string> = {
  valid: '有效', expiring: '即将过期', expired: '已过期',
  invalid: '配置异常', unconfigured: '未配置',
};
const purposeNames: Record<string, string> = { panel: '管理面板证书', subscription: '订阅服务证书' };

export default function CertificatesPage() {
  const navigate = useNavigate();
  const [certs, setCerts] = useState<Certificate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [alertsEnabled, setAlertsEnabled] = useState<boolean | null>(null);
  const pending = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    pending.current?.abort();
    const request = new AbortController();
    pending.current = request;
    setLoading(true);
    setError('');
    try {
      // HttpUtil._respToMsg keeps only success/msg/obj from the API envelope.
      // All certificate metadata (including alert state) must live inside obj.
      const response = await HttpUtil.get<{
        certificates: Certificate[];
        alertsEnabled: boolean;
      }>('/panel/api/certificates/status', undefined, { silent: true, signal: request.signal, timeout: 15_000 });
      if (request.signal.aborted) return;
      if (!response.success || !response.obj || !Array.isArray(response.obj.certificates)
        || typeof response.obj.alertsEnabled !== 'boolean') {
        throw new Error('invalid certificate response');
      }
      setCerts(response.obj.certificates);
      setAlertsEnabled(response.obj.alertsEnabled);
    } catch {
      if (!request.signal.aborted) setError('证书信息读取失败，请检查网络及管理员权限后刷新。');
    } finally {
      if (pending.current === request && !request.signal.aborted) {
        pending.current = null;
        setLoading(false);
      }
    }
  }, []);
  useEffect(() => {
    void refresh();
    return () => pending.current?.abort();
  }, [refresh]);
  const expiring = certs.filter((cert) => cert.status === 'expiring' || cert.status === 'expired' || cert.status === 'invalid').length;

  return (
    <Layout className="tg-cert-root">
      <AppSidebar />
      <Layout.Content className="tg-cert-content">
        <div className="tg-cert-container">
          <header className="tg-cert-header">
            <div>
              <div className="tg-cert-kicker">VELA · SECURITY CENTER</div>
              <h1>证书管理</h1>
              <p>统一查看 TLS 证书、有效期及配置状态</p>
            </div>
            <Button icon={<ReloadOutlined />} onClick={() => void refresh()} loading={loading}>刷新</Button>
          </header>
          <section className="tg-cert-overview" aria-label="证书概览">
            <div className="tg-cert-summary-item"><SafetyCertificateOutlined /><span>已接入证书</span><strong>{certs.filter(c => c.status !== 'unconfigured').length}</strong></div>
            <div className="tg-cert-summary-item"><WarningOutlined /><span>需关注</span><strong>{expiring}</strong></div>
          </section>
          {alertsEnabled !== null && <Alert
            type={alertsEnabled ? 'info' : 'warning'}
            showIcon
            className="tg-cert-alert"
            message={alertsEnabled ? 'Telegram 到期提醒已启用' : 'Telegram 到期提醒尚未启用'}
            description={alertsEnabled
              ? '每天按面板时区 09:00 检查管理面板和订阅证书，只通知授权的私人 Telegram 账号；消息不含域名、IP 或私钥路径。'
              : '为保护隐私，此功能默认关闭。管理员可在服务器本地配置 XUI_TG_CERT_ALERT_ENABLED=true 后重启 Vela。'}
          />}
          {error && <Alert type="error" message={error} showIcon className="tg-cert-alert" />}
          <Spin spinning={loading} description="正在检查证书…">
            <div className="tg-cert-list">
              {certs.map((cert) => (
                <article className="tg-cert-card" key={cert.purpose}>
                  <div className="tg-cert-card-top">
                    <div className="tg-cert-title"><span className="tg-cert-symbol"><SafetyCertificateOutlined /></span><span>{purposeNames[cert.purpose] || cert.purpose}</span></div>
                    <Tag color={cert.status === 'valid' ? 'success' : cert.status === 'expiring' ? 'warning' : cert.status === 'unconfigured' ? 'default' : 'error'}>
                      {stateNames[cert.status] || cert.status}
                    </Tag>
                  </div>
                  <div className="tg-cert-domain">{cert.dnsNames?.join(' · ') || '尚未读取到域名'}</div>
                  <div className="tg-cert-details">
                    <div><span>签发机构</span><strong>{cert.issuer || '—'}</strong></div>
                    <div><span>有效期至</span><strong>{cert.validUntil ? new Date(cert.validUntil).toLocaleDateString('zh-CN') : '—'}</strong></div>
                    <div><span>剩余天数</span><strong>{cert.status === 'expired' ? '已过期' : cert.validUntil ? `${cert.daysRemaining} 天` : '—'}</strong></div>
                    <div><span>密钥匹配</span><strong>{cert.status === 'unconfigured' ? '未配置' : cert.status === 'invalid' ? '需检查' : '已核验'}</strong></div>
                  </div>
                  <div className="tg-cert-actions">
                    <span>{cert.status === 'valid' ? <CheckCircleOutlined /> : <ClockCircleOutlined />} {cert.status === 'valid' ? '证书检查通过' : '请核实证书配置'}</span>
                    <Button onClick={() => navigate('/settings#general')} icon={<SettingOutlined />}>设置证书</Button>
                  </div>
                </article>
              ))}
            </div>
          </Spin>
          <p className="tg-cert-notice">此页提供证书状态和每日 Telegram 到期提醒设置说明。证书文件在面板设置中配置，签发和续签由部署环境负责。</p>
        </div>
      </Layout.Content>
    </Layout>
  );
}
