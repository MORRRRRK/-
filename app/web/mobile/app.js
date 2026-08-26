const ACCESS_KEY = 'finance_access_code';
const API_BASE = '';

function getAccessCode() {
  return localStorage.getItem(ACCESS_KEY) || '';
}

function setAccessCode(code) {
  localStorage.setItem(ACCESS_KEY, code);
}

async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', 'X-Access-Code': getAccessCode() };
  const resp = await fetch(API_BASE + path, { ...options, headers });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.error || '请求失败');
  return data;
}

function money(v) {
  return Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function typeText(t) {
  return { expense: '支出', income: '收入', transfer: '转账' }[t] || t;
}

function amountHtml(t, v) {
  const sign = t === 'expense' ? '-' : (t === 'income' ? '+' : '');
  const cls = t === 'expense' ? 'expense' : (t === 'income' ? 'income' : '');
  return `<span class="${cls}">${sign}${money(v)}</span>`;
}

async function requireAccess() {
  let code = getAccessCode();
  while (!code) {
    code = prompt('请输入局域网访问码');
    if (code) setAccessCode(code);
  }
}

function navActive() {
  const page = location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('nav.bottom a').forEach((a) => {
    a.classList.toggle('active', a.getAttribute('href') === page);
  });
}
