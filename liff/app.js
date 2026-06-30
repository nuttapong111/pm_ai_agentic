const API_BASE = window.location.origin + '/v1';
let token = localStorage.getItem('pm_token') || '';
let activeProject = null;
let projects = [];

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
    throw new Error(err.detail || err.message || res.statusText);
  }
  if (res.status === 204) return null;
  return res.json();
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
    await liff.init({ liffId: window.LIFF_ID || '' });
    if (!liff.isLoggedIn()) {
      liff.login();
      return;
    }
    const idToken = liff.getIDToken();
    const data = await api('/auth/line', { method: 'POST', body: { idToken } });
    token = data.accessToken;
    localStorage.setItem('pm_token', token);
  }

  activeProject = await api('/me/active-project');
  projects = await api('/projects');

  loading.classList.add('hidden');
  page.classList.remove('hidden');
  nav.classList.remove('hidden');

  window.addEventListener('hashchange', render);
  if (!location.hash) location.hash = '#/dashboard';
  render();
  } catch (e) {
    loading.textContent = 'เกิดข้อผิดพลาด: ' + e.message;
  }
}

function header(title, sub = '') {
  return `<div class="liff-header"><div class="grow"><div class="name">${title}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div></div>`;
}

function setNavActive(route) {
  document.querySelectorAll('[data-nav]').forEach(a => {
    a.classList.toggle('active', a.dataset.nav === route);
  });
}

async function render() {
  const route = (location.hash || '#/dashboard').slice(2).split('/')[0];
  const page = document.getElementById('page');
  setNavActive(route === 'projects' ? 'projects' : route === 'members' ? 'members' : route === 'settings' || route === 'connections' || route === 'numbering' || route === 'notifications' ? 'settings' : 'dashboard');

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
    return `<div class="list-row" data-action="select-project" data-id="${p.id}">
      <span class="${active ? 's-accent' : 's-muted'} mono">${p.key}</span>
      <div class="grow"><div>${p.name}</div>${active ? '<div class="sub2">โปรเจกต์ปัจจุบัน</div>' : ''}</div>
      ${active ? '<span class="s-success">✓</span>' : ''}
    </div>`;
  }).join('');
  return header('โปรเจกต์') + `<div class="admin-body"><div class="list">${rows}
    <button class="link-row" data-action="create-project">+ สร้างโปรเจกต์ใหม่</button></div></div>`;
}

async function viewDashboard() {
  if (!activeProject?.projectId) {
    return header('แดชบอร์ด') + '<div class="admin-body"><p>ยังไม่ได้เลือกโปรเจกต์ <a href="#/projects">เลือกโปรเจกต์</a></p></div>';
  }
  const d = await api(`/projects/${activeProject.projectId}/dashboard`);
  const pid = activeProject.projectId;
  const dueRows = (d.dueSoon || []).map(t => {
    const overdue = t.dueDate && new Date(t.dueDate) < new Date();
    return `<div class="list-row"><span class="grow">${t.title}</span><span class="sub2" style="color:${overdue ? '#dc2626' : '#b45309'}">${t.dueDate || '-'}</span></div>`;
  }).join('');
  const ms = d.nextMilestone;
  const msBar = ms ? `<div class="box"><div style="display:flex;justify-content:space-between;margin-bottom:7px;"><span>${ms.name}</span><span class="sub2">${ms.targetDate || ''}</span></div>
    <div class="bar"><span style="width:${ms.linkedTaskCount ? Math.min(100, ms.linkedTaskCount * 20) : 0}%"></span></div></div>` : '<p class="sub2">ยังไม่มี milestone</p>';
  const evt = d.nextEvent;
  const evtBox = evt ? `<div class="box" style="display:flex;gap:9px;"><span>📅</span><div><div>${evt.title}</div><div class="sub2">${new Date(evt.startsAt).toLocaleString('th-TH')}</div></div></div>` : '';
  return header(activeProject.name || 'แดชบอร์ด', 'แดชบอร์ด') + `<div class="admin-body">
    <div class="stats">
      <div class="stat"><div class="num">${d.taskCounts?.total || 0}</div><div class="lbl">งานทั้งหมด</div></div>
      <div class="stat"><div class="num" style="color:#b45309">${d.taskCounts?.pending || 0}</div><div class="lbl">ค้าง</div></div>
      <div class="stat"><div class="num" style="color:#15803d">${d.taskCounts?.done || 0}</div><div class="lbl">เสร็จ</div></div>
    </div>
    <div class="sec-label">Milestone</div>${msBar}
    <div class="sec-label">งานใกล้ครบกำหนด</div><div class="list">${dueRows || '<div class="list-row"><span class="sub2">ไม่มีงานใกล้ครบ</span></div>'}</div>
    <div class="sec-label">ประชุมถัดไป</div>${evtBox || '<p class="sub2">ไม่มีนัดหมาย</p>'}
  </div>`;
}

async function viewMembers() {
  if (!activeProject?.projectId) return header('สมาชิก') + '<div class="admin-body"><p>เลือกโปรเจกต์ก่อน</p></div>';
  const members = await api(`/projects/${activeProject.projectId}/members`);
  const rows = members.map(m => `<div class="list-row">
    <div class="grow"><div>${m.name}</div><div class="sub2">${m.email || '-'}</div></div>
    <span class="sub2">${m.role || ''}</span>
    <button class="s-danger" data-action="delete-member" data-id="${m.id}" style="border:none;background:none;cursor:pointer">ลบ</button>
  </div>`).join('');
  return header('สมาชิกโปรเจกต์', activeProject.name) + `<div class="admin-body"><div class="list">${rows}
    <button class="link-row" data-action="add-member">+ เพิ่มสมาชิก</button></div></div>`;
}

async function viewConnections() {
  const conns = await api('/connections');
  const types = ['clickup', 'jira', 'google', 'gmail'];
  const available = types.map(t => `<div class="list-row" data-action="authorize" data-type="${t}">
    <span class="grow">${t}</span><span class="s-accent">เชื่อมต่อ</span></div>`).join('');
  const connected = conns.map(c => `<div class="list-row">
    <span class="grow">${c.displayName}</span><span class="s-success">${c.status}</span>
    <button data-action="delete-connection" data-id="${c.id}" style="border:none;background:none;cursor:pointer;color:#dc2626">ลบ</button>
  </div>`).join('');
  return header('เชื่อมต่อแพลตฟอร์ม') + `<div class="admin-body">
    <div class="sec-label">เชื่อมแล้ว</div><div class="list">${connected || '<div class="list-row"><span class="sub2">ยังไม่มี</span></div>'}</div>
    <div class="sec-label">เพิ่มการเชื่อมต่อ</div><div class="list">${available}</div>
    <p class="sub2">เชื่อมครั้งเดียวใช้ได้ทุกโปรเจกต์ (OAuth)</p>
  </div>`;
}

async function viewBindings() {
  if (!activeProject?.projectId) return header('การเชื่อมต่อ') + '<div class="admin-body"><p>เลือกโปรเจกต์ก่อน</p></div>';
  const bindings = await api(`/projects/${activeProject.projectId}/bindings`);
  const caps = ['tasks', 'calendar', 'docs', 'email'];
  const rows = caps.map(cap => {
    const b = bindings.find(x => x.capability === cap);
    return `<div class="list-row"><span class="grow">${cap}</span><span class="sub2">${b ? b.connectionId.slice(0,8) + '…' : 'ยังไม่ตั้ง'}</span></div>`;
  }).join('');
  const templates = await api(`/projects/${activeProject.projectId}/templates`);
  const wpTypes = ['meeting_record', 'memo', 'traceability'];
  const tplRows = wpTypes.map(wp => {
    const has = templates.some(t => t.wpType === wp);
    return `<div class="list-row"><span class="grow">${wp}</span><span class="${has ? 's-success' : 's-muted'}">${has ? 'มีแล้ว' : 'ยังไม่มี'}</span>
      <button data-action="upload-template" data-wp="${wp}" style="border:none;background:none;cursor:pointer;color:#2563eb">อัปโหลด</button></div>`;
  }).join('');
  return header('การเชื่อมต่อ', activeProject.name) + `<div class="admin-body">
    <div class="sec-label">ปลายทาง capability</div><div class="list">${rows}</div>
    <div class="sec-label">เทมเพลตเอกสาร (.docx)</div><div class="list">${tplRows}</div>
  </div>`;
}

async function viewNumbering() {
  if (!activeProject?.projectId) return header('เลขเอกสาร') + '<div class="admin-body"><p>เลือกโปรเจกต์ก่อน</p></div>';
  const rules = await api(`/projects/${activeProject.projectId}/numbering`);
  const rows = rules.map(r => `<div class="list-row"><span class="grow">${r.wpType}</span><span class="s-accent mono">${r.prefix}</span><span class="sub2">ล่าสุด ${String(r.currentSeq).padStart(4,'0')}</span></div>`).join('');
  return header('เลขเอกสาร', activeProject.name) + `<div class="admin-body">
    <div class="box"><div class="mono sub2">{KEY}-{TYPE}-{SEQ:04d}</div><div class="mono" style="font-size:17px;font-weight:500;margin-top:5px">${activeProject.key}-MIN-0007</div></div>
    <div class="sec-label">ต่อชนิดเอกสาร</div><div class="list">${rows}</div>
  </div>`;
}

async function viewDocuments() {
  if (!activeProject?.projectId) return header('เอกสาร') + '<div class="admin-body"><p>เลือกโปรเจกต์ก่อน</p></div>';
  const data = await api(`/projects/${activeProject.projectId}/documents`);
  const rows = (data.items || []).map(d => `<div class="list-row">
    <div class="grow"><div>${d.title}</div><div class="sub2 mono">${d.docNumber || 'DRAFT'} · ${new Date(d.createdAt).toLocaleDateString('th-TH')}</div></div>
    <button data-action="download-doc" data-id="${d.id}" style="border:none;background:none;cursor:pointer">⬇</button>
  </div>`).join('');
  return header('เอกสาร', activeProject.name) + `<div class="admin-body"><div class="list">${rows || '<div class="list-row"><span class="sub2">ยังไม่มีเอกสาร</span></div>'}</div></div>`;
}

async function viewTraceability() {
  if (!activeProject?.projectId) return header('Traceability') + '<div class="admin-body"><p>เลือกโปรเจกต์ก่อน</p></div>';
  const cov = await api(`/projects/${activeProject.projectId}/traceability`);
  const covered = cov.filter(c => c.coverage === 'covered').length;
  const rows = cov.map(c => {
    const badge = c.coverage === 'covered' ? 's-success' : c.coverage === 'missing_test' ? 's-warn' : 's-danger';
    const label = c.coverage === 'covered' ? 'ครอบคลุม' : c.coverage === 'missing_test' ? 'ขาด test' : 'ยังไม่มีงาน';
    return `<div class="trow"><div style="display:flex;gap:7px;margin-bottom:7px"><span class="s-accent mono">${c.code}</span><span class="grow">${c.title}</span><span class="${badge}">${label}</span></div>
      <div class="sub2">งาน: ${(c.taskKeys||[]).join(', ') || '-'} · test: ${(c.testCaseCodes||[]).join(', ') || '-'}</div></div>`;
  }).join('');
  return header('Traceability', `${activeProject.name} · ครอบคลุม ${covered}/${cov.length}`) + `<div class="admin-body">${rows || '<p class="sub2">ยังไม่มี requirement</p>'}</div>`;
}

async function viewNotifications() {
  const prefs = await api('/me/notification-preferences');
  const types = [
    ['due_soon', 'งานใกล้ครบกำหนด'],
    ['overdue', 'งานเลยกำหนด'],
    ['meeting_soon', 'ใกล้ถึงเวลาประชุม'],
    ['status_change', 'สถานะงานเปลี่ยน'],
    ['milestone_due', 'milestone ใกล้ถึง'],
  ];
  const enabled = new Set(prefs.enabledTypes || []);
  const rows = types.map(([t, label]) => `<div class="list-row" data-action="toggle-notif" data-type="${t}">
    <span class="grow">${label}</span><span class="toggle ${enabled.has(t) ? 'on' : 'off'}"></span></div>`).join('');
  const quietOn = !!prefs.quietHoursStart;
  return header('การแจ้งเตือน') + `<div class="admin-body">
    <div class="sec-label">ชนิดการแจ้งเตือน</div><div class="list">${rows}</div>
    <div class="sec-label">ช่วงเวลางดรบกวน</div>
    <div class="list-row" style="border:1px solid var(--border);border-radius:11px">
      <span class="grow">ไม่ส่งช่วง ${prefs.quietHoursStart || '22:00'} – ${prefs.quietHoursEnd || '07:00'}</span>
      <span class="toggle ${quietOn ? 'on' : 'off'}" data-action="quiet-hours"></span>
    </div>
  </div>`;
}

function viewSettings() {
  return header('ตั้งค่า') + `<div class="admin-body"><div class="list">
    <a class="list-row" href="#/connections" style="text-decoration:none;color:inherit"><span class="grow">เชื่อมต่อแพลตฟอร์ม</span>›</a>
    <a class="list-row" href="#/bindings" style="text-decoration:none;color:inherit"><span class="grow">ปลายทาง + เทมเพลต</span>›</a>
    <a class="list-row" href="#/numbering" style="text-decoration:none;color:inherit"><span class="grow">เลขเอกสาร</span>›</a>
    <a class="list-row" href="#/documents" style="text-decoration:none;color:inherit"><span class="grow">คลังเอกสาร</span>›</a>
    <a class="list-row" href="#/traceability" style="text-decoration:none;color:inherit"><span class="grow">Traceability</span>›</a>
    <a class="list-row" href="#/notifications" style="text-decoration:none;color:inherit"><span class="grow">การแจ้งเตือน</span>›</a>
  </div></div>`;
}

init();
