import { describe, expect, it } from 'vitest';
import { authConfigured, authMode, buildAuthorizeUrl, readCookie, stateCookieValue, validStateCookie } from './account.js';

describe('微信账号授权 helpers', () => {
  it('只有完整的 D1、应用和状态密钥配置才启用账号功能', () => {
    expect(authConfigured({})).toBe(false);
    expect(authConfigured({ DB: {}, WECHAT_APP_ID: 'wx1', WECHAT_APP_SECRET: 'secret' })).toBe(false);
    expect(authConfigured({ DB: {}, WECHAT_APP_ID: 'wx1', WECHAT_APP_SECRET: 'secret', AUTH_STATE_SECRET: 'state' })).toBe(true);
  });

  it('生成网站扫码登录地址并保留回调参数', () => {
    const request = new Request('https://app.example.com/');
    const url = new URL(buildAuthorizeUrl(request, { WECHAT_APP_ID: 'wx1', WECHAT_AUTH_MODE: 'website' }, 'state123'));
    expect(url.hostname).toBe('open.weixin.qq.com');
    expect(url.pathname).toBe('/connect/qrconnect');
    expect(url.searchParams.get('appid')).toBe('wx1');
    expect(url.searchParams.get('state')).toBe('state123');
    expect(url.searchParams.get('scope')).toBe('snsapi_login');
    expect(authMode({ WECHAT_AUTH_MODE: 'official' })).toBe('official');
  });

  it('签名状态只能由原始密钥验证', async () => {
    const value = await stateCookieValue('abc', 'secret');
    expect(await validStateCookie(value, 'secret')).toBe('abc');
    expect(await validStateCookie(value, 'wrong')).toBe('');
  });

  it('读取指定 Cookie 而不误取同名前缀', () => {
    const request = new Request('https://app.example.com/', { headers: { Cookie: 'foo=1; richeng_session=token; richeng_session_old=old' } });
    expect(readCookie(request, 'richeng_session')).toBe('token');
  });
});
