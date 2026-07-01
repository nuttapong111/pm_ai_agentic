const API_BASE = window.location.origin + '/v1';
let token = localStorage.getItem('pm_token') || '';
let activeProject = null;
let projects = [];

function formatApiError(err) {
  if (!err) return '';
  const d = err.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join(', ');
  return err.message || '';
}

async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (opts.body && !(opts.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(opts.body);
  }
  const res = await fetch(API_BASE + path, { ...opts, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const msg = formatApiError(err) || res.statusText || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  if (res.status === 204) return null;
  return res.json();
}

async function getLiffId() {
  if (window.LIFF_ID) return window.LIFF_ID;
  const res = await fetch(API_BASE + '/liff/config');
  if (!res.ok) throw new Error('ไม่สามารถโหลด LIFF config ได้');
  const data = await res.json();
  window.LIFF_ID = data.liffId || '';
  return window.LIFF_ID;
}

async function init() {
  const loading = document.getElementById('loading');
  const page = document.getElementById('page');
  const nav = document.getElementById('nav');

  try {
  if (location.hostname === 'localhost' || location.search.includes('dev=1')) {
    if (!token) {
      const r = await fetch(API_BASE + '/auth/line', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idToken: 'dev:local-dev-user' }),
      });
      const data = await r.json();
      token = data.accessToken;
      localStorage.setItem('pm_token', token);
    }
  } else if (typeof liff !== 'undefined') {
    const liffId = await getLiffId();
    if (!liffId) throw new Error('ไม่พบ LIFF ID — ตั้ง LINE_LIFF_ID บน server');
    await liff.init({ liffId });
    if (!liff.isLoggedIn()) {
      liff.login();
      return;
    }
    const idToken = liff.getIDToken();
    if (!idToken) throw new Error('ยังไม่ได้ login LINE — ลองปิดแล้วเปิดใหม่');
    const data = await api('/auth/line', { method: 'POST', body: { idToken } });
    token = data.accessToken;
    localStorage.setItem('pm_token', token);
  }

  activeProject = await api('/me/active-project');
  projects = await api('/projects');

  const pageParam = new URLSearchParams(location.search).get('page');
  if (pageParam) location.hash = '#/' + pageParam;
  else if (!location.hash) location.hash = '#/dashboard';

  loading.classList.add('hidden');
  page.classList.remove('hidden');
  nav.classList.remove('hidden');

  window.addEventListener('hashchange', render);
  render();
  } catch (e) {
    const msg = (e && e.message) ? e.message : String(e || 'ไม่ทราบสาเหตุ');
    loading.textContent = 'เกิดข้อผิดพลาด: ' + msg;
  }
}

const WP_LABELS = {
  meeting_record: 'บันทึกการประชุม',
  memo: 'Memo',
  project_plan: 'Project Plan',
  requirements: 'Requirements',
  traceability: 'Traceability',
  test_case: 'Test Case',
  change_request: 'Change Request',
};

const CAP_LABELS = {
  tasks: 'งาน',
  calendar: 'ปฏิทิน',
  docs: 'เอกสาร',
  email: 'อีเมล',
};

const CAP_ICONS = {
  tasks: 'ti-clipboard-check',
  calendar: 'ti-calendar',
  docs: 'ti-file-text',
  email: 'ti-mail',
};

const PLATFORMS = [
  { type: 'clickup', label: 'ClickUp', icon: 'ti-layout-kanban' },
  { type: 'jira', label: 'Jira', icon: 'ti-brand-trello' },
  { type: 'google', label: 'Google', icon: 'ti-brand-google' },
];

const DOC_ICONS = {
  meeting_record: 'ti-file-text',
  memo: 'ti-mail',
  project_plan: 'ti-layout-list',
  default: 'ti-file',
};

function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
}

function header(title, sub = '', opts = {}) {
  const back = opts.back
    ? `<a href="${opts.back}" class="header-btn muted"><i class="ti ti-chevron-left"></i></a>`
    : '';
  let right = '';
  if (opts.close) {
    right = `<button type="button" class="header-btn muted" data-action="close-liff"><i class="ti ti-x"></i></button>`;
  } else if (opts.switch) {
    right = `<a href="#/projects" class="header-btn muted"><i class="ti ti-switch-horizontal"></i></a>`;
  } else if (opts.search) {
    right = `<span class="header-btn muted"><i class="ti ti-search"></i></span>`;
  }
  return `<div class="liff-header">${back}<div class="grow"><div class="name">${esc(title)}</div>${sub ? `<div class="sub">${esc(sub)}</div>` : ''}</div>${right}</div>`;
}

function formatDueLabel(dueDate) {
  if (!dueDate) return '-';
  const due = new Date(dueDate);
  const now = new Date();
  const diff = Math.ceil((due - now) / (1000 * 60 * 60 * 24));
  if (diff < 0) return `เลย ${Math.abs(diff)} วัน`;
  if (diff === 0) return 'วันนี้';
  if (diff === 1) return 'พรุ่งนี้';
  return due.toLocaleDateString('th-TH', { day: 'numeric', month: 'short' });
}

function dueColor(dueDate) {
  if (!dueDate) return 'var(--text-secondary)';
  const due = new Date(dueDate);
  const now = new Date();
  const diff = Math.ceil((due - now) / (1000 * 60 * 60 * 24));
  if (diff < 0) return 'var(--text-danger)';
  if (diff <= 1) return 'var(--text-warning)';
  return 'var(--text-secondary)';
}

function setNavActive(route) {
  document.querySelectorAll('[data-nav]').forEach(a => {
    a.classList.toggle('active', a.dataset.nav === route);
  });
}

async function render() {
  const route = (location.hash || '#/dashboard').slice(2).split('/')[0];
  const page = document.getElementById('page');
  setNavActive(
    route === 'projects' ? 'projects'
    : route === 'members' ? 'members'
    : ['settings', 'connections', 'bindings', 'numbering', 'notifications'].includes(route) ? 'settings'
    : 'dashboard'
  );

  try {
    switch (route) {
      case 'projects': page.innerHTML = await viewProjects(); break;
      case 'dashboard': page.innerHTML = await viewDashboard(); break;
      case 'members': page.innerHTML = await viewMembers(); break;
      case 'connections': page.innerHTML = await viewConnections(); break;
      case 'bindings': page.innerHTML = await viewBindings(); break;
      case 'numbering': page.innerHTML = await viewNumbering(); break;
      case 'documents': page.innerHTML = await viewDocuments(); break;
      case 'traceability': page.innerHTML = await viewTraceability(); break;
      case 'notifications': page.innerHTML = await viewNotifications(); break;
      case 'settings': page.innerHTML = viewSettings(); break;
      default: page.innerHTML = await viewDashboard();
    }
    bindEvents();
  } catch (e) {
    page.innerHTML = header('ข้อผิดพลาด') + `<div class="admin-body"><p>${e.message}</p></div>`;
  }
}

function bindEvents() {
  document.querySelectorAll('[data-action]').forEach(el => {
    el.onclick = async (e) => {
      e.preventDefault();
      const action = el.dataset.action;
      if (action === 'select-project') {
        await api('/me/active-project', { method: 'PUT', body: { projectId: el.dataset.id } });
        activeProject = await api('/me/active-project');
        location.hash = '#/dashboard';
      }
      if (action === 'create-project') {
        const key = prompt('รหัสโปรเจกต์ (เช่น HR):');
        const name = prompt('ชื่อโปรเจกต์:');
        if (key && name) {
          await api('/projects', { method: 'POST', body: { key, name } });
          projects = await api('/projects');
          render();
        }
      }
      if (action === 'add-member') {
        const name = prompt('ชื่อ:');
        const email = prompt('อีเมล:');
        const role = prompt('บทบาท:');
        if (name && activeProject?.projectId) {
          await api(`/projects/${activeProject.projectId}/members`, { method: 'POST', body: { name, email, role } });
          render();
        }
      }
      if (action === 'delete-member') {
        if (confirm('ลบสมาชิก?')) {
          await api(`/members/${el.dataset.id}`, { method: 'DELETE' });
          render();
        }
      }
      if (action === 'authorize') {
        const type = el.dataset.type;
        const r = await api('/connections/authorize', { method: 'POST', body: { type } });
        window.open(r.authorizationUrl, '_blank');
      }
      if (action === 'delete-connection') {
        if (confirm('ยกเลิกการเชื่อมต่อ?')) {
          await api(`/connections/${el.dataset.id}`, { method: 'DELETE' });
          render();
        }
      }
      if (action === 'toggle-notif') {
        const type = el.dataset.type;
        const prefs = await api('/me/notification-preferences');
        const types = new Set(prefs.enabledTypes || []);
        types.has(type) ? types.delete(type) : types.add(type);
        await api('/me/notification-preferences', { method: 'PUT', body: { ...prefs, enabledTypes: [...types] } });
        render();
      }
      if (action === 'download-doc') {
        const r = await api(`/documents/${el.dataset.id}/download`);
        window.open(r.downloadUrl, '_blank');
      }
      if (action === 'upload-template') {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.docx';
        input.onchange = async () => {
          const fd = new FormData();
          fd.append('wpType', el.dataset.wp);
          fd.append('file', input.files[0]);
          await api(`/projects/${activeProject.projectId}/templates`, { method: 'POST', body: fd });
          alert('อัปโหลดสำเร็จ');
          render();
        };
        input.click();
      }
      if (action === 'close-liff') {
        if (typeof liff !== 'undefined' && liff.closeWindow) liff.closeWindow();
        else history.back();
      }
      if (action === 'doc-tab') {
        document.querySelectorAll('[data-doc-tab]').forEach(t => t.classList.toggle('on', t.dataset.docTab === el.dataset.tab));
        document.querySelectorAll('[data-doc-item]').forEach(row => {
          const show = el.dataset.tab === 'all' || row.dataset.docType === el.dataset.tab;
          row.classList.toggle('hidden', !show);
        });
      }
    };
  });

  document.querySelectorAll('.toggle[data-action="quiet-hours"]').forEach(el => {
    el.onclick = async () => {
      const prefs = await api('/me/notification-preferences');
      const on = !prefs.quietHoursStart;
      await api('/me/notification-preferences', {
        method: 'PUT',
        body: { ...prefs, quietHoursStart: on ? '22:00' : null, quietHoursEnd: on ? '07:00' : null },
      });
      render();
    };
  });
}

async function viewProjects() {
  projects = await api('/projects');
  const rows = projects.map(p => {
    const active = activeProject?.projectId === p.id;
    return `<div class="list-row clickable" data-action="select-project" data-id="${p.id}">
      <span class="key-badge ${active ? 'active' : 'inactive'}">${esc(p.key)}</span>
      <div class="grow"><div>${esc(p.name)}</div>${active ? '<div class="sub2">โปรเจกต์ปัจจุบัน</div>' : ''}</div>
      ${active ? '<i class="ti ti-circle-check-filled icon-success" style="font-size:19px"></i>' : ''}
    </div>`;
  }).join('');
  return header('โปรเจกต์', '', { close: true }) + `<div class="admin-body"><div class="list">${rows || '<div class="list-row"><span class="sub2">ยังไม่มีโปรเจกต์</span></div>'}
    <button type="button" class="link-row" data-action="create-project"><i class="ti ti-plus"></i>สร้างโปรเจกต์ใหม่</button></div></div>`;
}

async function viewDashboard() {
  if (!activeProject?.projectId) {
    return header('แดชบอร์ด', '', { switch: true }) + `<div class="empty-state">ยังไม่ได้เลือกโปรเจกต์<br><a href="#/projects">เลือกโปรเจกต์</a></div>`;
  }
  const d = await api(`/projects/${activeProject.projectId}/dashboard`);
  const dueRows = (d.dueSoon || []).map(t => `<div class="list-row">
    <span class="grow">${esc(t.title)}</span>
    <span class="sub2" style="color:${dueColor(t.dueDate)}">${formatDueLabel(t.dueDate)}</span>
  </div>`).join('');
  const ms = d.nextMilestone;
  const linked = ms?.linkedTaskCount ?? 0;
  const pct = linked ? 40 : 0;
  const msBar = ms
    ? `<div class="box"><div style="display:flex;justify-content:space-between;margin-bottom:7px"><span style="font-size:12.5px">${esc(ms.name)}</span><span class="sub2">${ms.targetDate ? new Date(ms.targetDate).toLocaleDateString('th-TH', { day: 'numeric', month: 'short' }) : ''}</span></div>
      <div class="bar"><span style="width:${pct}%"></span></div>
      <div class="sub2" style="margin-top:5px">${linked} งานที่ผูกกับ milestone</div></div>`
    : '<div class="box"><span class="sub2">ยังไม่มี milestone</span></div>';
  const evt = d.nextEvent;
  const evtBox = evt
    ? `<div class="box meeting"><i class="ti ti-calendar-event"></i><div><div style="font-size:12.5px">${esc(evt.title)}</div><div class="sub2">${new Date(evt.startsAt).toLocaleString('th-TH', { weekday: 'short', hour: '2-digit', minute: '2-digit' })}${evt.meetLink ? ' · Google Meet' : ''}</div></div></div>`
    : '<div class="box"><span class="sub2">ไม่มีนัดหมายถัดไป</span></div>';
  return header(activeProject.name || 'แดชบอร์ด', 'แดชบอร์ด', { switch: true }) + `<div class="admin-body">
    <div class="stats">
      <div class="stat"><div class="num">${d.taskCounts?.total || 0}</div><div class="lbl">งานทั้งหมด</div></div>
      <div class="stat"><div class="num" style="color:var(--text-warning)">${d.taskCounts?.pending || 0}</div><div class="lbl">ค้าง</div></div>
      <div class="stat"><div class="num" style="color:var(--text-success)">${d.taskCounts?.done || 0}</div><div class="lbl">เสร็จ</div></div>
    </div>
    <div class="sec-label">Milestone</div>${msBar}
    <div class="sec-label">งานใกล้ครบกำหนด</div>
    <div class="list">${dueRows || '<div class="list-row"><span class="sub2">ไม่มีงานใกล้ครบ</span></div>'}</div>
    <div class="sec-label">ประชุมถัดไป</div>${evtBox}
  </div>`;
}

async function viewMembers() {
  if (!activeProject?.projectId) {
    return header('สมาชิกโปรเจกต์', '', { close: true }) + `<div class="empty-state"><a href="#/projects">เลือกโปรเจกต์ก่อน</a></div>`;
  }
  const members = await api(`/projects/${activeProject.projectId}/members`);
  const rows = members.map(m => {
    const initial = (m.name || '?').charAt(0);
    return `<div class="list-row">
      <div class="avatar">${esc(initial)}</div>
      <div class="grow"><div>${esc(m.name)}</div><div class="sub2">${esc(m.email || '-')}</div></div>
      <span class="sub2">${esc(m.role || '')}</span>
      <button type="button" class="header-btn muted" data-action="delete-member" data-id="${m.id}" title="ลบ"><i class="ti ti-trash" style="font-size:15px;color:var(--text-danger)"></i></button>
    </div>`;
  }).join('');
  return header('สมาชิกโปรเจกต์', `${activeProject.name} · ${members.length} คน`, { close: true }) + `<div class="admin-body"><div class="list">${rows || '<div class="list-row"><span class="sub2">ยังไม่มีสมาชิก</span></div>'}
    <button type="button" class="link-row" data-action="add-member"><i class="ti ti-user-plus"></i>เพิ่มสมาชิก</button></div></div>`;
}

async function viewConnections() {
  const conns = await api('/connections');
  const byType = Object.fromEntries(conns.map(c => [c.type, c]));
  const rows = PLATFORMS.map(p => {
    const c = byType[p.type];
    const status = c
      ? '<span class="sub2" style="color:var(--text-success)">เชื่อมแล้ว</span>'
      : '<span class="s-accent">เชื่อมต่อ</span>';
    const action = c ? '' : `data-action="authorize" data-type="${p.type}"`;
    return `<div class="list-row clickable" ${action}><i class="ti ${p.icon} icon-muted"></i><span class="grow">${p.label}</span>${status}</div>`;
  }).join('');
  return header('เชื่อมต่อแพลตฟอร์ม', '', { back: '#/settings' }) + `<div class="admin-body">
    <div class="list">${rows}</div>
    <p class="note"><i class="ti ti-lock" style="font-size:13px;vertical-align:-2px"></i> กดเชื่อมต่อจะพาไปหน้าอนุญาตสิทธิ์ (OAuth) เชื่อมครั้งเดียวใช้ได้ทุกโปรเจกต์</p>
  </div>`;
}

async function viewBindings() {
  if (!activeProject?.projectId) {
    return header('การเชื่อมต่อ', '', { close: true }) + `<div class="empty-state"><a href="#/projects">เลือกโปรเจกต์ก่อน</a></div>`;
  }
  const bindings = await api(`/projects/${activeProject.projectId}/bindings`);
  const caps = ['tasks', 'calendar', 'docs', 'email'];
  const capRows = caps.map(cap => {
    const b = bindings.find(x => x.capability === cap);
    const dest = b ? `${String(b.connectionId).slice(0, 8)}…` : 'ยังไม่ตั้ง';
    return `<div class="list-row"><i class="ti ${CAP_ICONS[cap]} icon-muted"></i><span class="grow">${CAP_LABELS[cap]}</span><span class="sub2">${esc(dest)}</span><i class="ti ti-chevron-down icon-muted"></i></div>`;
  }).join('');
  const templates = await api(`/projects/${activeProject.projectId}/templates`);
  const wpTypes = ['meeting_record', 'memo', 'traceability'];
  const tplRows = wpTypes.map(wp => {
    const has = templates.some(t => t.wpType === wp);
    const right = has
      ? '<span class="s-success">มีแล้ว</span><i class="ti ti-refresh icon-muted"></i>'
      : '<span class="s-muted">ยังไม่มี</span><button type="button" class="header-btn accent" data-action="upload-template" data-wp="' + wp + '"><i class="ti ti-upload"></i></button>';
    return `<div class="list-row"><i class="ti ${wp === 'memo' ? 'ti-mail' : wp === 'traceability' ? 'ti-git-branch' : 'ti-file-text'} icon-muted"></i><span class="grow">${WP_LABELS[wp] || wp}</span>${right}</div>`;
  }).join('');
  return header('การเชื่อมต่อ', `โปรเจกต์ ${activeProject.name}`, { close: true }) + `<div class="admin-body">
    <div class="sec-label">ปลายทางของโปรเจกต์นี้</div><div class="list">${capRows}</div>
    <div class="sec-label">เทมเพลตเอกสาร</div><div class="list">${tplRows}</div>
  </div>`;
}

async function viewNumbering() {
  if (!activeProject?.projectId) {
    return header('เลขเอกสาร', '', { close: true }) + `<div class="empty-state"><a href="#/projects">เลือกโปรเจกต์ก่อน</a></div>`;
  }
  const rules = await api(`/projects/${activeProject.projectId}/numbering`);
  const yearly = rules.some(r => r.resetPeriod === 'yearly');
  const sample = rules[0];
  const sampleNum = sample ? `${activeProject.key}-${sample.prefix}-${String(sample.currentSeq).padStart(4, '0')}` : `${activeProject.key}-MIN-0001`;
  const rows = rules.map(r => `<div class="list-row"><span class="grow">${WP_LABELS[r.wpType] || r.wpType}</span><span class="s-accent mono">${esc(r.prefix)}</span><span class="sub2">ล่าสุด ${String(r.currentSeq).padStart(4, '0')}</span></div>`).join('');
  return header('เลขเอกสาร', `โปรเจกต์ ${activeProject.name}`, { close: true }) + `<div class="admin-body">
    <div class="sec-label">รูปแบบเลขเอกสาร</div>
    <div class="box"><div class="mono sub2">{KEY}-{TYPE}-{เลขรัน 4 หลัก}</div><div class="mono" style="font-size:17px;font-weight:500;margin-top:5px">${esc(sampleNum)}</div></div>
    <div class="toggle-row"><span class="grow">รีเซ็ตเลขรันทุกปี</span><span class="toggle ${yearly ? 'on' : 'off'}"></span></div>
    <div class="sec-label">ต่อชนิดเอกสาร</div><div class="list">${rows || '<div class="list-row"><span class="sub2">ยังไม่ตั้งเลขเอกสาร</span></div>'}</div>
  </div>`;
}

async function viewDocuments() {
  if (!activeProject?.projectId) {
    return header('เอกสาร', '', { search: true }) + `<div class="empty-state"><a href="#/projects">เลือกโปรเจกต์ก่อน</a></div>`;
  }
  const data = await api(`/projects/${activeProject.projectId}/documents`);
  const items = data.items || [];
  const rows = items.map(d => {
    const icon = DOC_ICONS[d.wpType] || DOC_ICONS.default;
    return `<div class="list-row" data-doc-item data-doc-type="${d.wpType || 'other'}">
      <i class="ti ${icon} icon-muted"></i>
      <div class="grow"><div>${esc(d.title)}</div><div class="sub2 mono">${esc(d.docNumber || 'DRAFT')} · ${new Date(d.createdAt).toLocaleDateString('th-TH', { day: 'numeric', month: 'short' })}</div></div>
      <button type="button" class="header-btn muted" data-action="download-doc" data-id="${d.id}"><i class="ti ti-download"></i></button>
    </div>`;
  }).join('');
  return header('เอกสาร', activeProject.name, { search: true }) + `<div class="admin-body">
    <div class="tabs">
      <span class="tab on" data-action="doc-tab" data-tab="all" data-doc-tab="all">ทั้งหมด</span>
      <span class="tab" data-action="doc-tab" data-tab="meeting_record" data-doc-tab="meeting_record">บันทึกประชุม</span>
      <span class="tab" data-action="doc-tab" data-tab="memo" data-doc-tab="memo">Memo</span>
    </div>
    <div class="list">${rows || '<div class="list-row"><span class="sub2">ยังไม่มีเอกสาร</span></div>'}</div>
  </div>`;
}

async function viewTraceability() {
  if (!activeProject?.projectId) {
    return header('Traceability', '', { close: true }) + `<div class="empty-state"><a href="#/projects">เลือกโปรเจกต์ก่อน</a></div>`;
  }
  const cov = await api(`/projects/${activeProject.projectId}/traceability`);
  const covered = cov.filter(c => c.coverage === 'covered').length;
  const rows = cov.map(c => {
    const badge = c.coverage === 'covered' ? 's-success' : c.coverage === 'missing_test' ? 's-warn' : 's-danger';
    const label = c.coverage === 'covered' ? 'ครอบคลุม' : c.coverage === 'missing_test' ? 'ขาด test' : 'ยังไม่มีงาน';
    const tasks = (c.taskKeys || []).join(', ') || 'ยังไม่มี task';
    const tests = (c.testCaseCodes || []).join(', ') || 'ยังไม่มี test case';
    const subStyle = c.coverage === 'no_task' ? ' style="color:var(--text-danger)"' : '';
    return `<div class="trow"><div style="display:flex;align-items:center;gap:7px;margin-bottom:7px">
      <span class="s-accent mono">${esc(c.code)}</span><span class="grow" style="font-size:12.5px">${esc(c.title)}</span><span class="${badge}">${label}</span></div>
      <div class="sub2"${subStyle}><i class="ti ti-clipboard-check" style="font-size:12px;vertical-align:-2px"></i> ${esc(tasks)} · <i class="ti ti-checklist" style="font-size:12px;vertical-align:-2px"></i> ${esc(tests)}</div></div>`;
  }).join('');
  return header('Traceability', `${activeProject.name} · ครอบคลุม ${covered}/${cov.length}`, { close: true }) + `<div class="admin-body">${rows || '<p class="sub2">ยังไม่มี requirement</p>'}</div>`;
}

async function viewNotifications() {
  const prefs = await api('/me/notification-preferences');
  const types = [
    ['due_soon', 'งานใกล้ครบกำหนด'],
    ['overdue', 'งานเลยกำหนด'],
    ['meeting_soon', 'ใกล้ถึงเวลาประชุม'],
    ['status_change', 'สถานะงานเปลี่ยน', true],
    ['milestone_due', 'milestone ใกล้ถึง'],
  ];
  const enabled = new Set(prefs.enabledTypes || []);
  const rows = types.map(([t, label, muted]) => `<div class="list-row clickable" data-action="toggle-notif" data-type="${t}">
    <span class="grow${muted && !enabled.has(t) ? ' muted' : ''}">${label}</span><span class="toggle ${enabled.has(t) ? 'on' : 'off'}"></span></div>`).join('');
  const quietOn = !!prefs.quietHoursStart;
  return header('การแจ้งเตือน', '', { close: true }) + `<div class="admin-body">
    <div class="sec-label">ชนิดการแจ้งเตือน</div><div class="list">${rows}</div>
    <div class="sec-label">ช่วงเวลางดรบกวน</div>
    <div class="toggle-row"><i class="ti ti-moon icon-muted"></i><span class="grow">ไม่ส่งช่วง</span><span class="sub2 mono">${prefs.quietHoursStart || '22:00'} – ${prefs.quietHoursEnd || '07:00'}</span><span class="toggle ${quietOn ? 'on' : 'off'}" data-action="quiet-hours"></span></div>
  </div>`;
}

function viewSettings() {
  const items = [
    { href: '#/connections', icon: 'ti-plug-connected', label: 'เชื่อมต่อแพลตฟอร์ม' },
    { href: '#/bindings', icon: 'ti-link', label: 'ปลายทาง + เทมเพลต' },
    { href: '#/numbering', icon: 'ti-hash', label: 'เลขเอกสาร' },
    { href: '#/documents', icon: 'ti-files', label: 'คลังเอกสาร' },
    { href: '#/traceability', icon: 'ti-git-branch', label: 'Traceability' },
    { href: '#/notifications', icon: 'ti-bell', label: 'การแจ้งเตือน' },
  ];
  const rows = items.map(i => `<a class="list-row clickable" href="${i.href}"><i class="ti ${i.icon} icon-muted"></i><span class="grow">${i.label}</span><i class="ti ti-chevron-right icon-muted"></i></a>`).join('');
  return header('ตั้งค่า', '', { close: true }) + `<div class="admin-body"><div class="list">${rows}</div></div>`;
}

init();
