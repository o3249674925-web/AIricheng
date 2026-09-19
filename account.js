export const SESSION_COOKIE = 'richeng_session';
export const STATE_COOKIE = 'richeng_oauth_state';
export const SESSION_DAYS = 30;
export const STATE_SECONDS = 600;

export function authConfigured(env) {
  return Boolean(env?.DB && env?.WECHAT_APP_ID && env?.WECHAT_APP_SECRET && env?.AUTH_STATE_SECRET);
}

export function authMode(env) {
  return env?.WECHAT_AUTH_MODE === 'official' ? 'official' : 'website';
}

export function redirectUri(request, env) {
  return env?.WECHAT_REDIRECT_URI || new URL('/api/auth/wechat/callback', request.url).toString();
}

export function buildAuthorizeUrl(request, env, state) {
  const mode = authMode(env);
  const endpoint = mode === 'official'
    ? 'https://open.weixin.qq.com/connect/oauth2/authorize'
    : 'https://open.weixin.qq.com/connect/qrconnect';
  const params = new URLSearchParams({
    appid: env.WECHAT_APP_ID,
    redirect_uri: redirectUri(request, env),
    response_type: 'code',
    scope: mode === 'official' ? (env.WECHAT_SCOPE === 'snsapi_userinfo' ? 'snsapi_userinfo' : 'snsapi_base') : 'snsapi_login',
    state,
  });
  return `${endpoint}?${params.toString()}#wechat_redirect`;
}

export function readCookie(request, name) {
  const header = request.headers.get('Cookie') || '';
  for (const item of header.split(';')) {
    const [key, ...rest] = item.trim().split('=');
    if (key === name) return rest.join('=');
  }
  return '';
}

export function cookie(name, value, maxAge) {
  return `${name}=${value}; Max-Age=${maxAge}; Path=/; HttpOnly; Secure; SameSite=Lax`;
}

export function clearCookie(name) {
  return cookie(name, '', 0);
}

export async function randomHex(bytes = 24) {
  const data = new Uint8Array(bytes);
  crypto.getRandomValues(data);
  return Array.from(data, value => value.toString(16).padStart(2, '0')).join('');
}

function base64Url(bytes) {
  let binary = '';
  for (const value of bytes) binary += String.fromCharCode(value);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

async function hmac(value, secret) {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  return base64Url(new Uint8Array(await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(value))));
}

export async function stateCookieValue(state, secret) {
  return `${state}.${await hmac(state, secret)}`;
}

export async function validStateCookie(value, secret) {
  const [state, signature] = String(value || '').split('.');
  if (!state || !signature) return '';
  const expected = await hmac(state, secret);
  return signature === expected ? state : '';
}

export async function sha256Hex(value) {
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value)));
  return Array.from(digest, byte => byte.toString(16).padStart(2, '0')).join('');
}

export async function exchangeWeChatCode(code, env) {
  const params = new URLSearchParams({
    appid: env.WECHAT_APP_ID,
    secret: env.WECHAT_APP_SECRET,
    code,
    grant_type: 'authorization_code',
  });
  const response = await fetch(`https://api.weixin.qq.com/sns/oauth2/access_token?${params.toString()}`);
  if (!response.ok) throw new Error('wechat_exchange_failed');
  let body;
  try { body = await response.json(); } catch { throw new Error('wechat_exchange_failed'); }
  if (!body?.openid || !body?.access_token || body?.errcode) throw new Error('wechat_exchange_failed');
  return body;
}

export async function fetchWeChatProfile(token, openid, env) {
  if (env.WECHAT_FETCH_PROFILE !== 'true') return {};
  const params = new URLSearchParams({ access_token: token, openid, lang: 'zh_CN' });
  try {
    const response = await fetch(`https://api.weixin.qq.com/sns/userinfo?${params.toString()}`);
    if (!response.ok) return {};
    const body = await response.json();
    return body?.errcode ? {} : {
      displayName: typeof body?.nickname === 'string' ? body.nickname.slice(0, 80) : '',
      avatarUrl: typeof body?.headimgurl === 'string' ? body.headimgurl.slice(0, 500) : '',
    };
  } catch { return {}; }
}
