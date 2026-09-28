/**
 * Nurse Roster 12h - Modern Interactive Frontend Application
 * Handles grid rendering, keyboard shortcuts, continuous shift painting,
 * auto-solving, live rule validation, and Excel import/export.
 */

// Global State
let state = {
  ward: 'W6A',
  month: 'ตุลาคม',
  year: '2569',
  days: Array.from({ length: 31 }, (_, i) => i + 1),
  weekdays: ['พฤ', 'ศ', 'ส', 'อา', 'จ', 'อ', 'พ', 'พฤ', 'ศ', 'ส', 'อา', 'จ', 'อ', 'พ', 'พฤ', 'ศ', 'ส', 'อา', 'จ', 'อ', 'พ', 'พฤ', 'ศ', 'ส', 'อา', 'จ', 'อ', 'พ', 'พฤ', 'ศ', 'ส'],
  nurses: [],
  tailShifts: {},
  rules: {
    max_consec_work: 4,
    max_consec_plain_off: 2,
    cap_C4: 11,
    cap_CK: 4,
    cap_P4: 8,
    need_C4: 3,
    need_P4: 2,
    ck_counts_as_day: true,
    require_senior_per_shift: true
  },
  selectedPalette: 'C4',
  isLockMode: false,
  isTailPanelOpen: false,
  ignoreTail: false,
  violations: [],
  isMouseDown: false,
  activeCell: null,
  isSolving: false,
  searchTerm: '',
  activeFilter: 'ALL',
  isDarkMode: false
};

// Shift Definitions & Hours
const SHIFT_HOURS = {
  'C4': 12,
  'P4': 12,
  'CK': 16,
  'TRAIN': 12,
  'c': 12
};

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
  fetchInitialData();
  setupGlobalEvents();
});

// Setup Mouse & Keyboard Listeners
function setupGlobalEvents() {
  document.addEventListener('mouseup', () => {
    state.isMouseDown = false;
  });

  document.addEventListener('keydown', handleGlobalKeydown);
  initDarkMode();

  // Close dropdown when clicked outside
  document.addEventListener('click', (e) => {
    const menu = document.getElementById('batch-menu');
    if (menu && !menu.contains(e.target) && !e.target.closest('button[onclick="toggleBatchMenu()"]')) {
      menu.classList.add('hidden');
    }
  });
}

// Fetch Initial Ward Data
async function fetchInitialData() {
  try {
    const res = await fetch('/api/initial');
    if (!res.ok) throw new Error('Cannot load initial data');
    const data = await res.json();

    state.ward = data.ward || 'W6A';
    state.month = data.month || 'ตุลาคม';
    state.year = data.year || '2569';
    state.days = data.days || Array.from({ length: 31 }, (_, i) => i + 1);
    state.weekdays = data.weekdays || [];
    state.nurses = data.nurses || [];
    state.tailShifts = data.default_tail || {};

    // Ensure locked array exists
    state.nurses.forEach(n => {
      if (!n.locked) {
        n.locked = n.grid.map(c => c !== null);
      }
    });

    document.getElementById('ward-badge').textContent = `แผนก ${state.ward}`;
    document.getElementById('roster-month-year').textContent = `${state.month} ${state.year}`;

    renderTable();
    renderTailInputs();
    validateRoster();
    selectPalette('C4');

  } catch (err) {
    console.error(err);
    showToast('เกิดข้อผิดพลาดในการโหลดข้อมูล: ' + err.message, true);
  }
}

// Render Main Table
function renderTable() {
  renderDaysHeader();
  renderWeekdaysHeader();
  renderTableBody();
  renderTableFooter();
  updateDashboardCards();
}

// Render Days in Header Row 1
function renderDaysHeader() {
  const tr = document.querySelector('thead tr.sticky-top-1');
  const oldThs = tr.querySelectorAll('th.day-header-cell');
  oldThs.forEach(th => th.remove());

  const marker = document.getElementById('days-header-marker');

  state.days.forEach((day, dIdx) => {
    const th = document.createElement('th');
    th.className = 'day-header-cell border-r border-slate-200 px-1 py-1 text-center font-bold text-xs min-w-[38px]';
    
    // Weekend styling
    const wday = state.weekdays[dIdx] || '';
    const isWeekend = wday === 'ส' || wday === 'อา';
    if (isWeekend) {
      th.classList.add('bg-slate-200', 'text-sky-900');
    } else {
      th.classList.add('bg-slate-100');
    }
    th.textContent = day;
    tr.insertBefore(th, marker);
  });
}

// Render Weekdays in Header Row 2
function renderWeekdaysHeader() {
  const tr = document.getElementById('weekdays-header-row');
  const oldThs = tr.querySelectorAll('th.weekday-cell');
  oldThs.forEach(th => th.remove());

  // Insert before summary colspan
  const summaryTh = tr.querySelector('th[colspan="7"]');

  state.days.forEach((_, dIdx) => {
    const wday = state.weekdays[dIdx] || '';
    const th = document.createElement('th');
    th.className = 'weekday-cell border-r border-slate-200 px-1 py-0.5 text-center text-[10px] font-semibold';
    if (wday === 'ส' || wday === 'อา') {
      th.classList.add('bg-amber-100', 'text-amber-800');
    }
    th.textContent = wday;
    tr.insertBefore(th, summaryTh);
  });
}

// Render Nurse Rows
function renderTableBody() {
  const tbody = document.getElementById('roster-tbody');
  tbody.innerHTML = '';

  let visibleCount = 0;

  state.nurses.forEach((nurse, nIdx) => {
    // Filter by search
    if (state.searchTerm) {
      const matchName = (nurse.name || '').toLowerCase().includes(state.searchTerm);
      const matchCode = (nurse.code || '').toLowerCase().includes(state.searchTerm);
      if (!matchName && !matchCode) return;
    }

    // Filter by level
    if (state.activeFilter === 'SENIOR') {
      if (!(nurse.level || '').toLowerCase().includes('senior')) return;
    } else if (state.activeFilter === 'RN2') {
      if ((nurse.level || '').toLowerCase().includes('senior')) return;
    }

    visibleCount++;
    const tr = document.createElement('tr');
    tr.className = 'hover:bg-slate-50 transition border-b border-slate-200';

    // 1. ลำดับ
    const tdNo = document.createElement('td');
    tdNo.className = 'sticky-left-1 bg-white px-2 py-1.5 border-r border-slate-200 text-center font-medium text-slate-500';
    tdNo.textContent = nurse.no || (nIdx + 1);
    tr.appendChild(tdNo);

    // 2. รหัส
    const tdCode = document.createElement('td');
    tdCode.className = 'sticky-left-2 bg-white px-2 py-1.5 border-r border-slate-200 text-center font-mono text-[11px] text-slate-600';
    tdCode.textContent = nurse.code || '-';
    tr.appendChild(tdCode);

    // 3. ชื่อ - นามสกุล (พร้อม Avatar & ป้าย Seniority & ปุ่มการ์ดเวร)
    const tdName = document.createElement('td');
    tdName.className = 'sticky-left-3 bg-white px-3 py-2 border-r border-slate-200 text-left whitespace-nowrap shadow-[2px_0_5px_-2px_rgba(0,0,0,0.05)]';
    
    const isSenior = (nurse.level || '').toLowerCase().includes('senior');
    const badgeClass = isSenior ? 'badge-senior' : 'badge-rn2';
    const badgeText = isSenior ? 'Senior' : (nurse.level || 'RN');
    const avatarColor = isSenior 
      ? 'bg-purple-100 text-purple-700 border border-purple-200' 
      : 'bg-sky-100 text-sky-700 border border-sky-200';
    const initial = (nurse.name || 'N').trim().charAt(0);

    tdName.innerHTML = `
      <div class="flex items-center justify-between group">
        <div class="flex items-center space-x-2">
          <div class="w-6 h-6 rounded-full ${avatarColor} flex items-center justify-center text-[10px] font-bold shadow-xs">
            ${initial}
          </div>
          <span class="nurse-name-btn font-bold text-slate-800 hover:text-sky-600 transition" onclick="openNurseModal(${nIdx})" title="คลิกเพื่อดูตารางเวรส่วนบุคคลและโหลดปฏิทิน">
            ${nurse.name}
          </span>
          <span class="${badgeClass}">${badgeText}</span>
        </div>
        <button onclick="openNurseModal(${nIdx})" class="opacity-0 group-hover:opacity-100 text-sky-600 hover:text-sky-800 p-1 transition" title="ดูการ์ดเวร & ส่ง LINE">
          <i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i>
        </button>
      </div>
    `;
    tr.appendChild(tdName);

    // 4. F/NF
    const tdFnf = document.createElement('td');
    tdFnf.className = 'px-1.5 py-1.5 border-r border-slate-200 text-center text-[11px] text-slate-500';
    tdFnf.textContent = nurse.fnf || '';
    tr.appendChild(tdFnf);

    // 5. Level
    const tdLevel = document.createElement('td');
    tdLevel.className = 'px-2 py-1.5 border-r border-slate-200 text-center text-[11px] text-slate-600 font-medium whitespace-nowrap';
    tdLevel.textContent = nurse.level || '';
    tr.appendChild(tdLevel);

    // Tail columns (D-3, D-2, D-1, D-0)
    const tailList = getTailList(nurse);
    for (let b = 0; b < 4; b++) {
      const tdTail = document.createElement('td');
      const tailCode = tailList[b] || '-';
      tdTail.className = `tail-col border-r border-sky-200 text-center text-[11px] font-bold shift-${tailCode} ${b === 3 ? 'border-r-2 border-sky-300' : ''}`;
      tdTail.textContent = tailCode === '-' ? '·' : tailCode;
      tdTail.title = `เวรเดือนก่อน: วันที่ -${4 - b}`;
      tr.appendChild(tdTail);
    }

    // Days 1..31
    state.days.forEach((_, dIdx) => {
      const code = nurse.grid[dIdx];
      const isLocked = nurse.locked ? nurse.locked[dIdx] : false;

      const td = document.createElement('td');
      td.className = `shift-cell border-r border-slate-200 ${code ? 'shift-' + code : 'shift-off'}`;
      if (isLocked) td.classList.add('cell-locked');

      td.dataset.nurse = nIdx;
      td.dataset.day = dIdx;
      td.textContent = (code === '-' || code === null) ? (code === '-' ? '·' : '') : (code === 'TRAIN' ? 'c' : code);

      // Event handlers for fast editing
      td.addEventListener('mousedown', (e) => {
        state.isMouseDown = true;
        handleCellAction(nIdx, dIdx, e);
      });

      td.addEventListener('mouseenter', (e) => {
        if (state.isMouseDown) {
          handleCellAction(nIdx, dIdx, e);
        }
      });

      td.addEventListener('focus', () => {
        state.activeCell = { nurse: nIdx, day: dIdx };
      });

      td.addEventListener('mouseenter', () => {
        highlightCrosshair(nIdx, dIdx);
      });

      td.addEventListener('mouseleave', () => {
        clearCrosshair();
      });

      tr.appendChild(td);
    });

    // Summary Columns
    const counts = calculateNurseTotals(nurse);

    // C4
    const tdC4 = document.createElement('td');
    tdC4.className = `border-l-2 border-slate-300 border-r border-slate-200 text-center font-bold ${counts.C4 > state.rules.cap_C4 ? 'text-red-600 bg-red-50' : 'text-amber-800 bg-amber-50/50'}`;
    tdC4.textContent = counts.C4 || '-';
    tr.appendChild(tdC4);

    // CK
    const tdCK = document.createElement('td');
    tdCK.className = `border-r border-slate-200 text-center font-bold ${counts.CK > state.rules.cap_CK ? 'text-red-600 bg-red-50' : 'text-orange-900 bg-orange-50/50'}`;
    tdCK.textContent = counts.CK || '-';
    tr.appendChild(tdCK);

    // P4
    const tdP4 = document.createElement('td');
    tdP4.className = `border-r border-slate-200 text-center font-bold ${counts.P4 > state.rules.cap_P4 ? 'text-red-600 bg-red-50' : 'text-indigo-900 bg-indigo-50/50'}`;
    tdP4.textContent = counts.P4 || '-';
    tr.appendChild(tdP4);

    // OFF
    const tdOff = document.createElement('td');
    tdOff.className = 'border-r border-slate-200 text-center font-semibold text-slate-700 bg-slate-100/50';
    tdOff.textContent = counts.OFF || '-';
    tr.appendChild(tdOff);

    // V
    const tdV = document.createElement('td');
    tdV.className = 'border-r border-slate-200 text-center font-semibold text-emerald-800 bg-emerald-50/50';
    tdV.textContent = counts.V || '-';
    tr.appendChild(tdV);

    // LP
    const tdLP = document.createElement('td');
    tdLP.className = 'border-r border-slate-200 text-center font-semibold text-red-800 bg-red-50/50';
    tdLP.textContent = counts.LP || '-';
    tr.appendChild(tdLP);

    // Total Hours
    const tdTotalHrs = document.createElement('td');
    tdTotalHrs.className = 'border-r border-slate-300 text-center font-bold text-sky-950 bg-sky-100/60';
    tdTotalHrs.textContent = counts.hours;
    tr.appendChild(tdTotalHrs);

    tbody.appendChild(tr);
  });
  const countSpan = document.getElementById('visible-nurse-count');
  if (countSpan) countSpan.textContent = visibleCount;
}

// Render Table Footer (Daily Staffing Coverage)
function renderTableFooter() {
  const tfoot = document.getElementById('roster-tfoot');
  tfoot.innerHTML = '';

  const D = state.days.length;

  // Row 1: Morning Staffing (C4 + CK)
  const trMorn = document.createElement('tr');
  trMorn.className = 'bg-amber-50/80 border-b border-slate-200 text-slate-700 text-xs';

  const tdLabelMorn = document.createElement('td');
  tdLabelMorn.className = 'sticky-left-1 bg-amber-50 text-left px-3 py-1.5 font-bold text-amber-900';
  tdLabelMorn.setAttribute('colspan', 5);
  tdLabelMorn.textContent = `เวรเช้า (C4${state.rules.ck_counts_as_day ? '+CK' : ''}) [เป้า ${state.rules.need_C4}]`;
  trMorn.appendChild(tdLabelMorn);

  // Skip tail columns
  for (let b = 0; b < 4; b++) {
    const td = document.createElement('td');
    td.className = 'tail-col bg-amber-50 border-r border-sky-200';
    trMorn.appendChild(td);
  }

  // Days 1..31
  state.days.forEach((_, dIdx) => {
    const count = state.nurses.reduce((acc, n) => {
      const code = n.grid[dIdx];
      return acc + (code === 'C4' || (state.rules.ck_counts_as_day && code === 'CK') ? 1 : 0);
    }, 0);

    const td = document.createElement('td');
    const diff = count - state.rules.need_C4;
    td.className = 'border-r border-slate-200 px-1 py-1.5 text-center font-bold';

    if (count === state.rules.need_C4) {
      td.classList.add('bg-emerald-100', 'text-emerald-800');
    } else if (count < state.rules.need_C4) {
      td.classList.add('bg-red-200', 'text-red-900');
      td.title = `ขาด ${Math.abs(diff)} คน`;
    } else {
      td.classList.add('bg-amber-200', 'text-amber-900');
      td.title = `เกิน ${diff} คน`;
    }
    td.textContent = count;
    trMorn.appendChild(td);
  });

  // Empty summary cells
  for (let i = 0; i < 7; i++) {
    trMorn.appendChild(document.createElement('td'));
  }
  tfoot.appendChild(trMorn);

  // Row 2: Night Staffing (P4)
  const trNight = document.createElement('tr');
  trNight.className = 'bg-indigo-50/80 text-slate-700 text-xs';

  const tdLabelNight = document.createElement('td');
  tdLabelNight.className = 'sticky-left-1 bg-indigo-50 text-left px-3 py-1.5 font-bold text-indigo-900';
  tdLabelNight.setAttribute('colspan', 5);
  tdLabelNight.textContent = `เวรดึก (P4) [เป้า ${state.rules.need_P4}]`;
  trNight.appendChild(tdLabelNight);

  for (let b = 0; b < 4; b++) {
    const td = document.createElement('td');
    td.className = 'tail-col bg-indigo-50 border-r border-sky-200';
    trNight.appendChild(td);
  }

  state.days.forEach((_, dIdx) => {
    const count = state.nurses.reduce((acc, n) => {
      return acc + (n.grid[dIdx] === 'P4' ? 1 : 0);
    }, 0);

    const td = document.createElement('td');
    const diff = count - state.rules.need_P4;
    td.className = 'border-r border-slate-200 px-1 py-1.5 text-center font-bold';

    if (count === state.rules.need_P4) {
      td.classList.add('bg-emerald-100', 'text-emerald-800');
    } else if (count < state.rules.need_P4) {
      td.classList.add('bg-red-200', 'text-red-900');
      td.title = `ขาด ${Math.abs(diff)} คน`;
    } else {
      td.classList.add('bg-amber-200', 'text-amber-900');
      td.title = `เกิน ${diff} คน`;
    }
    td.textContent = count;
    trNight.appendChild(td);
  });

  for (let i = 0; i < 7; i++) {
    trNight.appendChild(document.createElement('td'));
  }
  tfoot.appendChild(trNight);

  // Row 3: Senior RN Staffing
  const trSenior = document.createElement('tr');
  trSenior.className = 'bg-purple-50/70 text-slate-700 text-xs border-t border-purple-200';

  const tdLabelSr = document.createElement('td');
  tdLabelSr.className = 'sticky-left-1 bg-purple-50 text-left px-3 py-1.5 font-bold text-purple-950';
  tdLabelSr.setAttribute('colspan', 5);
  tdLabelSr.innerHTML = '<span class="flex items-center space-x-1"><i class="fa-solid fa-user-shield text-purple-600"></i> <span>Senior RN ในเวร (เช้า/ดึก)</span></span>';
  trSenior.appendChild(tdLabelSr);

  for (let b = 0; b < 4; b++) {
    const td = document.createElement('td');
    td.className = 'tail-col bg-purple-50 border-r border-sky-200';
    trSenior.appendChild(td);
  }

  state.days.forEach((_, dIdx) => {
    let mornSr = 0;
    let nightSr = 0;
    state.nurses.forEach(n => {
      const isSr = (n.level || '').toLowerCase().includes('senior');
      if (isSr) {
        if (n.grid[dIdx] === 'C4' || (state.rules.ck_counts_as_day && n.grid[dIdx] === 'CK')) mornSr++;
        if (n.grid[dIdx] === 'P4') nightSr++;
      }
    });

    const td = document.createElement('td');
    td.className = 'border-r border-slate-200 px-1 py-1 text-center font-bold text-[11px]';
    const ok = mornSr >= 1 && nightSr >= 1;
    if (ok) {
      td.classList.add('bg-purple-100', 'text-purple-900');
      td.title = `เช้า ${mornSr} คน, ดึก ${nightSr} คน (ผ่านเกณฑ์)`;
    } else {
      td.classList.add('bg-rose-100', 'text-rose-900');
      td.title = `ขาด Senior RN! (เช้า: ${mornSr}, ดึก: ${nightSr})`;
    }
    td.textContent = `${mornSr}/${nightSr}`;
    trSenior.appendChild(td);
  });

  for (let i = 0; i < 7; i++) {
    trSenior.appendChild(document.createElement('td'));
  }
  tfoot.appendChild(trSenior);
}

// Render Previous Month Tail Inputs Drawer
function renderTailInputs() {
  const container = document.getElementById('tail-inputs-container');
  container.innerHTML = '';

  state.nurses.forEach(nurse => {
    const card = document.createElement('div');
    card.className = 'bg-white p-2 rounded-lg border border-sky-100 shadow-sm flex items-center justify-between';

    const nameSpan = document.createElement('span');
    nameSpan.className = 'font-medium text-slate-800 truncate mr-2 max-w-[120px]';
    nameSpan.textContent = nurse.name;
    nameSpan.title = nurse.name;
    card.appendChild(nameSpan);

    const tailList = getTailList(nurse);

    const inputsDiv = document.createElement('div');
    inputsDiv.className = 'flex items-center space-x-1';

    for (let b = 0; b < 4; b++) {
      const select = document.createElement('select');
      select.className = 'text-[11px] font-bold border border-slate-300 rounded px-1 py-0.5 bg-slate-50 focus:bg-white';
      ['-', 'C4', 'P4', 'CK', 'X'].forEach(optCode => {
        const opt = document.createElement('option');
        opt.value = optCode;
        opt.textContent = optCode;
        if ((tailList[b] || '-') === optCode) opt.selected = true;
        select.appendChild(opt);
      });

      select.addEventListener('change', (e) => {
        updateTailShift(nurse.name, b, e.target.value);
      });
      inputsDiv.appendChild(select);
    }

    card.appendChild(inputsDiv);
    container.appendChild(card);
  });
}

function getTailList(nurse) {
  if (state.ignoreTail) return ['-', '-', '-', '-'];
  const name = nurse.name ? nurse.name.trim() : '';
  const fromName = state.tailShifts[name] || state.tailShifts[nurse.name];
  const fromNo = state.tailShifts[String(nurse.no)];
  const raw = fromName || fromNo || ['-', '-', '-', '-'];
  const copyList = [...raw];
  while (copyList.length < 4) copyList.unshift('-');
  return copyList.slice(-4);
}

function updateTailShift(nurseName, index, code) {
  const name = nurseName.trim();
  if (!state.tailShifts[name]) {
    state.tailShifts[name] = ['-', '-', '-', '-'];
  }
  state.tailShifts[name][index] = code;
  renderTable();
  validateRoster();
}

function toggleIgnoreTail(e) {
  state.ignoreTail = e.target.checked;
  renderTable();
  validateRoster();
  showToast(state.ignoreTail ? 'เริ่มนับใหม่จากวันที่ 1 แล้ว' : 'นำเวรท้ายเดือนก่อนมาคิดคำนวณแล้ว');
}

function applySampleTailPresets() {
  state.tailShifts = {
    'ฐานียา แสงงาม': ['C4', 'C4', 'P4', '-'],
    'ปิยาภรณ์ ดาราศร': ['X', 'X', 'C4', 'C4'],
    'อรอุมา มะลัยคำ': ['P4', 'P4', '-', '-'],
    'อรจิรา จิตราช': ['-', 'C4', 'C4', 'P4'],
    'ณัฐณิชา ติลบาล': ['C4', 'P4', '-', 'X'],
    'ปริชาติ นาคสู่สุข': ['-', '-', 'C4', 'C4'],
    'จิดาภา  โอฐงาม': ['P4', '-', 'X', 'C4'],
    'อภิญญา  แก่นมี': ['C4', 'C4', '-', '-']
  };
  renderTailInputs();
  renderTable();
  validateRoster();
  showToast('โหลดเวรท้ายเดือนก่อนตัวอย่างเรียบร้อย');
}

// Cell Interaction: Click & Drag Painting
function handleCellAction(nurseIdx, dayIdx, event) {
  const nurse = state.nurses[nurseIdx];
  if (!nurse) return;

  pushHistory();
  state.activeCell = { nurse: nurseIdx, day: dayIdx };

  // If Lock Mode is active: toggle lock on this cell
  if (state.isLockMode) {
    nurse.locked[dayIdx] = !nurse.locked[dayIdx];
    renderTable();
    return;
  }

  // Paint with selected palette code
  let newCode = state.selectedPalette;
  if (newCode === 'CLEAR') {
    newCode = null;
    nurse.locked[dayIdx] = false;
  } else {
    // If it's a leave or requested shift, automatically lock it
    if (['V', 'HBD', 'LK', 'LP', 'TRAIN', 'X'].includes(newCode)) {
      nurse.locked[dayIdx] = true;
    }
  }

  nurse.grid[dayIdx] = newCode;
  renderTable();
  validateRoster();
}

// Select Palette Tool
function selectPalette(code) {
  state.selectedPalette = code;
  document.querySelectorAll('.palette-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.shift === code);
  });
}

// Toggle Lock Mode Tool
function toggleLockMode() {
  state.isLockMode = !state.isLockMode;
  const btn = document.getElementById('btn-lock-mode');
  const icon = document.getElementById('lock-mode-icon');

  if (state.isLockMode) {
    btn.classList.add('bg-slate-800', 'text-white');
    icon.classList.remove('text-slate-500');
    icon.classList.add('text-amber-400');
    showToast('เปิดโหมดล็อกช่อง: คลิกช่องในตารางเพื่อล็อก/ปลดล็อก');
  } else {
    btn.classList.remove('bg-slate-800', 'text-white');
    icon.classList.add('text-slate-500');
    icon.classList.remove('text-amber-400');
    showToast('ปิดโหมดล็อกช่อง');
  }
}

// Toggle Tail Panel
function toggleTailPanel() {
  state.isTailPanelOpen = !state.isTailPanelOpen;
  const panel = document.getElementById('tail-panel');
  panel.classList.toggle('hidden', !state.isTailPanelOpen);
}

function toggleBatchMenu() {
  const menu = document.getElementById('batch-menu');
  menu.classList.toggle('hidden');
}

// Keyboard Shortcuts Handling
function handleGlobalKeydown(e) {
  if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return;

  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
    if (e.shiftKey) redo();
    else undo();
    e.preventDefault();
    return;
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') {
    redo();
    e.preventDefault();
    return;
  }

  const key = e.key.toUpperCase();

  if (key === 'C') selectPalette('C4');
  else if (key === 'P') selectPalette('P4');
  else if (key === 'K') selectPalette('CK');
  else if (key === 'X') selectPalette('X');
  else if (key === '-' || key === '_') selectPalette('-');
  else if (key === 'V') selectPalette('V');
  else if (key === 'B') selectPalette('HBD');
  else if (key === 'L') selectPalette('LK');
  else if (key === 'U') selectPalette('LP');
  else if (key === 'T') selectPalette('TRAIN');
  else if (key === 'DELETE' || key === 'BACKSPACE') selectPalette('CLEAR');

  if (state.activeCell) {
    const { nurse, day } = state.activeCell;
    const map = {
      'C': 'C4', 'P': 'P4', 'K': 'CK', 'X': 'X', '-': '-',
      'V': 'V', 'B': 'HBD', 'L': 'LK', 'U': 'LP', 'T': 'TRAIN'
    };
    if (map[key]) {
      state.selectedPalette = map[key];
      handleCellAction(nurse, day);
    } else if (key === 'DELETE' || key === 'BACKSPACE') {
      state.selectedPalette = 'CLEAR';
      handleCellAction(nurse, day);
    }
  }
}

// Calculate Totals per Nurse
function calculateNurseTotals(nurse) {
  const grid = nurse.grid || [];
  let c4 = 0, ck = 0, p4 = 0, off = 0, v = 0, lp = 0;

  grid.forEach(c => {
    if (c === 'C4') c4++;
    else if (c === 'CK') ck++;
    else if (c === 'P4') p4++;
    else if (c === 'V') { v++; off++; }
    else if (c === 'LP') { lp++; off++; }
    else if (['X', '-', 'HBD', 'LK', 'H'].includes(c)) off++;
  });

  const hours = (c4 * 12) + (ck * 16) + (p4 * 12);
  return { C4: c4, CK: ck, P4: p4, OFF: off, V: v, LP: lp, hours };
}

// Auto-Solve Scheduling via Backend OR-Tools
async function runAutoSolve() {
  if (state.isSolving) return;
  state.isSolving = true;

  const btn = document.getElementById('btn-solve');
  const icon = document.getElementById('solve-icon');
  btn.disabled = true;
  btn.classList.add('opacity-75', 'cursor-wait');
  icon.className = 'fa-solid fa-spinner animate-spin';

  showToast('กำลังประมวลผลจัดเวรด้วย Constraint Solver...', false);

  try {
    const payload = {
      nurses: state.nurses,
      days: state.days,
      rules: state.rules,
      prev_tail: state.ignoreTail ? {} : state.tailShifts,
      locked_grid: state.nurses.map(n => n.locked),
      allow_ck: true,
      time_limit: 30
    };

    const res = await fetch('/api/solve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();

    if (!data.success) {
      showToast(data.message || 'ไม่สามารถจัดเวรได้ตามเงื่อนไขที่ระบุ', true);
      openValidationModal();
    } else {
      state.nurses = data.nurses;
      renderTable();
      validateRoster();
      showToast(`จัดเวรสำเร็จ! ลงตารางใหม่ ${data.newly_assigned_count || 0} ช่อง`);
    }

  } catch (err) {
    console.error(err);
    showToast('เกิดข้อผิดพลาดในการเชื่อมต่อกับเซิร์ฟเวอร์: ' + err.message, true);
  } finally {
    state.isSolving = false;
    btn.disabled = false;
    btn.classList.remove('opacity-75', 'cursor-wait');
    icon.className = 'fa-solid fa-wand-magic-sparkles';
  }
}

// Validate Rules Real-time
async function validateRoster() {
  try {
    const payload = {
      nurses: state.nurses,
      days: state.days,
      rules: state.rules,
      prev_tail: state.ignoreTail ? {} : state.tailShifts
    };

    const res = await fetch('/api/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    state.violations = data.violations || [];
    updateValidationUI();

  } catch (err) {
    console.error('Validation error:', err);
  }
}

// Update Validation UI Badges & Pill
function updateValidationUI() {
  const pill = document.getElementById('status-pill');
  const pillIcon = document.getElementById('status-pill-icon');
  const pillText = document.getElementById('status-pill-text');
  const pillCount = document.getElementById('status-pill-count');

  // Clear previous cell violations
  document.querySelectorAll('.cell-violation').forEach(el => {
    el.classList.remove('cell-violation');
    el.removeAttribute('title');
  });

  const errors = state.violations.filter(v => v.severity === 'error');
  const warnings = state.violations.filter(v => v.severity === 'warning');

  if (state.violations.length === 0) {
    pill.className = 'hidden sm:flex items-center space-x-2 px-3 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 cursor-pointer hover:bg-emerald-100 transition';
    pillIcon.className = 'fa-solid fa-circle-check text-emerald-500 text-sm';
    pillText.textContent = 'ผ่านทุกกฎ 100%';
    pillCount.classList.add('hidden');
  } else {
    pill.className = 'hidden sm:flex items-center space-x-2 px-3 py-1 rounded-full text-xs font-medium bg-red-50 text-red-700 border border-red-200 cursor-pointer hover:bg-red-100 transition';
    pillIcon.className = 'fa-solid fa-triangle-exclamation text-red-500 text-sm';
    pillText.textContent = errors.length > 0 ? `พบกฎผิด ${errors.length} ข้อ` : `พบข้อสังเกต ${warnings.length} ข้อ`;
    pillCount.textContent = state.violations.length;
    pillCount.classList.remove('hidden');

    // Highlight violation cells on table
    state.violations.forEach(v => {
      if (v.nurse_index !== null && v.day !== null) {
        const cell = document.querySelector(`.shift-cell[data-nurse="${v.nurse_index}"][data-day="${v.day - 1}"]`);
        if (cell) {
          cell.classList.add('cell-violation');
          cell.title = v.message;
        }
      }
    });
  }
}

// Modals: Rules & Validation
function openRulesModal() {
  document.getElementById('rule-need-c4').value = state.rules.need_C4;
  document.getElementById('rule-need-p4').value = state.rules.need_P4;
  document.getElementById('rule-cap-c4').value = state.rules.cap_C4;
  document.getElementById('rule-cap-p4').value = state.rules.cap_P4;
  document.getElementById('rule-cap-ck').value = state.rules.cap_CK;
  document.getElementById('rule-max-work').value = state.rules.max_consec_work;
  document.getElementById('rule-ck-day').checked = state.rules.ck_counts_as_day;
  document.getElementById('rule-senior-shift').checked = state.rules.require_senior_per_shift !== false;

  document.getElementById('rules-modal').classList.remove('hidden');
}

function closeRulesModal() {
  document.getElementById('rules-modal').classList.add('hidden');
}

function saveRules() {
  state.rules.need_C4 = parseInt(document.getElementById('rule-need-c4').value) || 3;
  state.rules.need_P4 = parseInt(document.getElementById('rule-need-p4').value) || 2;
  state.rules.cap_C4 = parseInt(document.getElementById('rule-cap-c4').value) || 11;
  state.rules.cap_P4 = parseInt(document.getElementById('rule-cap-p4').value) || 8;
  state.rules.cap_CK = parseInt(document.getElementById('rule-cap-ck').value) || 4;
  state.rules.max_consec_work = parseInt(document.getElementById('rule-max-work').value) || 4;
  state.rules.ck_counts_as_day = document.getElementById('rule-ck-day').checked;
  state.rules.require_senior_per_shift = document.getElementById('rule-senior-shift').checked;

  closeRulesModal();
  renderTable();
  validateRoster();
  showToast('บันทึกกติกาใหม่เรียบร้อยแล้ว');
}

function resetDefaultRules() {
  document.getElementById('rule-need-c4').value = 3;
  document.getElementById('rule-need-p4').value = 2;
  document.getElementById('rule-cap-c4').value = 11;
  document.getElementById('rule-cap-p4').value = 8;
  document.getElementById('rule-cap-ck').value = 4;
  document.getElementById('rule-max-work').value = 4;
  document.getElementById('rule-ck-day').checked = true;
  document.getElementById('rule-senior-shift').checked = true;
}

function openValidationModal() {
  const modal = document.getElementById('validation-modal');
  const list = document.getElementById('validation-list');
  list.innerHTML = '';

  if (state.violations.length === 0) {
    list.innerHTML = `
      <div class="p-6 text-center text-emerald-700 bg-emerald-50 rounded-lg border border-emerald-200">
        <i class="fa-solid fa-circle-check text-4xl mb-2"></i>
        <h3 class="text-base font-bold">ตารางเวรสมบูรณ์แบบ!</h3>
        <p class="text-xs text-emerald-600 mt-1">ผ่านกฎระเบียบทั้ง 5 ข้อของหอผู้ป่วย ไม่มีข้อขัดแย้งหรือข้อสังเกตใดๆ</p>
      </div>
    `;
  } else {
    state.violations.forEach((v, idx) => {
      const item = document.createElement('div');
      const isErr = v.severity === 'error';
      item.className = `p-3 rounded-lg border flex items-start space-x-2.5 text-xs ${isErr ? 'bg-red-50 border-red-200 text-red-900' : 'bg-amber-50 border-amber-200 text-amber-900'}`;

      item.innerHTML = `
        <i class="fa-solid ${isErr ? 'fa-circle-xmark text-red-500' : 'fa-triangle-exclamation text-amber-500'} text-base mt-0.5"></i>
        <div class="flex-1">
          <span class="font-semibold">${v.message}</span>
        </div>
      `;
      list.appendChild(item);
    });
  }

  modal.classList.remove('hidden');
}

function closeValidationModal() {
  document.getElementById('validation-modal').classList.add('hidden');
}

// Batch Actions
function clearAutoShifts() {
  state.nurses.forEach(n => {
    n.grid.forEach((c, idx) => {
      if (!n.locked[idx] && ['C4', 'P4', 'CK', '-'].includes(c)) {
        n.grid[idx] = null;
      }
    });
  });
  renderTable();
  validateRoster();
  showToast('ล้างเฉพาะเวรที่ระบบจัดให้แล้ว (เก็บวันลาและเวรขอไว้ครบถ้วน)');
}

function lockAllCurrentShifts() {
  state.nurses.forEach(n => {
    n.locked = n.grid.map(c => c !== null);
  });
  renderTable();
  showToast('ล็อกเวรปัจจุบันทั้งหมดเรียบร้อย');
}

function unlockAllShifts() {
  state.nurses.forEach(n => {
    n.locked = n.grid.map(() => false);
  });
  renderTable();
  showToast('ปลดล็อกเวรทั้งหมดแล้ว');
}

function resetToDefaultData() {
  if (confirm('คุณต้องการรีเซ็ตข้อมูลตารางกลับเป็นค่าตั้งต้นใช่หรือไม่?')) {
    fetchInitialData();
    showToast('รีเซ็ตตารางเรียบร้อยแล้ว');
  }
}

// Excel Export
async function triggerExcelExport() {
  showToast('กำลังสร้างไฟล์ Excel...', false);
  try {
    const payload = {
      roster_data: {
        ward: state.ward,
        month: state.month,
        year: state.year,
        days: state.days,
        weekdays: state.weekdays,
        nurses: state.nurses
      },
      rules: state.rules,
      prev_tail: state.ignoreTail ? {} : state.tailShifts
    };

    const res = await fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) throw new Error('Export failed');

    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ตารางเวร_${state.ward}_${state.month}${state.year}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);

    showToast('ดาวน์โหลดไฟล์ Excel สำเร็จ!');
  } catch (err) {
    console.error(err);
    showToast('ส่งออก Excel ไม่สำเร็จ: ' + err.message, true);
  }
}

// Excel Upload
async function handleExcelUpload(event) {
  const file = event.target.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append('file', file);

  showToast('กำลังนำเข้าไฟล์ Excel...', false);

  try {
    const res = await fetch('/api/import', {
      method: 'POST',
      body: formData
    });

    if (!res.ok) throw new Error('Cannot import Excel');
    const data = await res.json();

    state.ward = data.ward || state.ward;
    state.month = data.month || state.month;
    state.year = data.year || state.year;
    state.days = data.days || state.days;
    state.weekdays = data.weekdays || state.weekdays;
    state.nurses = data.nurses || state.nurses;

    document.getElementById('ward-badge').textContent = `แผนก ${state.ward}`;
    document.getElementById('roster-month-year').textContent = `${state.month} ${state.year}`;

    renderTable();
    renderTailInputs();
    validateRoster();
    showToast(`นำเข้าสำเร็จ: ${state.nurses.length} พยาบาล (${state.month} ${state.year})`);

  } catch (err) {
    console.error(err);
    showToast('นำเข้า Excel ล้มเหลว: ' + err.message, true);
  } finally {
    event.target.value = '';
  }
}

// Toast Notifications
let toastTimeout;
function showToast(msg, isError = false) {
  const toast = document.getElementById('toast');
  const icon = document.getElementById('toast-icon');
  const text = document.getElementById('toast-message');

  clearTimeout(toastTimeout);

  text.textContent = msg;
  if (isError) {
    icon.className = 'fa-solid fa-circle-exclamation text-rose-400';
  } else {
    icon.className = 'fa-solid fa-circle-check text-emerald-400';
  }

  toast.classList.remove('translate-y-20', 'opacity-0', 'pointer-events-none');

  toastTimeout = setTimeout(() => {
    toast.classList.add('translate-y-20', 'opacity-0', 'pointer-events-none');
  }, 3200);
}


// Active Nurse Modal State
let activeNurseIdx = 0;

function openNurseModal(nIdx) {
  activeNurseIdx = nIdx;
  const nurse = state.nurses[nIdx];
  if (!nurse) return;

  const isSenior = (nurse.level || '').toLowerCase().includes('senior');
  document.getElementById('nm-avatar').textContent = (nurse.name || 'N').charAt(0);
  document.getElementById('nm-name').textContent = nurse.name;
  document.getElementById('nm-level').className = isSenior ? 'badge-senior' : 'badge-rn2';
  document.getElementById('nm-level').textContent = nurse.level || 'RN';
  document.getElementById('nm-subtitle').textContent = `รหัส ${nurse.code || '-'} • แผนก ${state.ward}`;

  const totals = calculateNurseTotals(nurse);
  document.getElementById('nm-c4').textContent = totals.C4;
  document.getElementById('nm-p4').textContent = totals.P4;
  document.getElementById('nm-off').textContent = totals.OFF;
  document.getElementById('nm-hours').textContent = totals.hours;

  // Render shift list
  const list = document.getElementById('nm-shift-list');
  list.innerHTML = '';

  state.days.forEach((day, dIdx) => {
    const code = nurse.grid[dIdx];
    const wday = state.weekdays[dIdx] || '';
    if (!code || code === '-') return;

    const row = document.createElement('div');
    row.className = 'flex items-center justify-between py-1 px-2 rounded bg-white border border-slate-100';

    let desc = code;
    let badgeClass = 'bg-slate-100 text-slate-700';

    if (code === 'C4') { desc = 'เวรเช้า (07:00 - 19:00)'; badgeClass = 'bg-amber-100 text-amber-900 border-amber-200'; }
    else if (code === 'P4') { desc = 'เวรดึก (19:00 - 07:00)'; badgeClass = 'bg-indigo-100 text-indigo-900 border-indigo-200'; }
    else if (code === 'CK') { desc = 'เวรพิเศษ 16 ชม. (07:00 - 23:00)'; badgeClass = 'bg-orange-100 text-orange-900 border-orange-200'; }
    else if (code === 'V') { desc = 'ลาพักร้อน'; badgeClass = 'bg-emerald-100 text-emerald-900 border-emerald-200'; }
    else if (code === 'HBD') { desc = 'วันเกิด'; badgeClass = 'bg-rose-100 text-rose-900 border-rose-200'; }
    else if (code === 'X') { desc = 'วันหยุดประจำสัปดาห์'; badgeClass = 'bg-slate-200 text-slate-800 border-slate-300'; }
    else if (code === 'TRAIN') { desc = 'อบรม/กิจกรรม'; badgeClass = 'bg-slate-100 text-slate-800 border-slate-200'; }

    row.innerHTML = `
      <div class="flex items-center space-x-2">
        <span class="font-bold text-slate-700 w-12">${day} (${wday})</span>
        <span class="text-slate-600 text-[11px]">${desc}</span>
      </div>
      <span class="px-2 py-0.5 rounded text-[10px] font-bold border ${badgeClass}">${code}</span>
    `;
    list.appendChild(row);
  });

  document.getElementById('nurse-modal').classList.remove('hidden');
}

function closeNurseModal() {
  document.getElementById('nurse-modal').classList.add('hidden');
}

async function downloadActiveNurseICS() {
  const nurse = state.nurses[activeNurseIdx];
  if (!nurse) return;

  showToast('กำลังเตรียมปฏิทิน .ics สำหรับมือถือ...', false);
  try {
    const payload = {
      nurse: nurse,
      month: state.month,
      year: state.year,
      ward: state.ward
    };

    const res = await fetch('/api/nurse-ics', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) throw new Error('ICS request failed');
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ตารางเวร_${nurse.name.trim()}_${state.month}.ics`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
    showToast(`ดาวน์โหลดปฏิทินของ ${nurse.name} สำเร็จ! กดเปิดเพื่อนำเข้ามือถือได้ทันที`);
  } catch (err) {
    showToast('ดาวน์โหลดปฏิทินไม่สำเร็จ: ' + err.message, true);
  }
}

function copyActiveNurseLine() {
  const nurse = state.nurses[activeNurseIdx];
  if (!nurse) return;

  const totals = calculateNurseTotals(nurse);
  let text = `🏥 *ตารางเวรเดือน ${state.month} ${state.year}*\n`;
  text += `👩‍⚕️ *พยาบาล:* ${nurse.name} (${nurse.level || 'RN'})\n`;
  text += `📍 *แผนก:* ${state.ward}\n`;
  text += `⏱️ *รวมชั่วโมง:* ${totals.hours} ชม.\n`;
  text += `☀️ เช้า (C4): ${totals.C4} วัน | 🌙 ดึก (P4): ${totals.P4} วัน\n`;
  if (totals.CK > 0) text += `⚡ พิเศษ (CK): ${totals.CK} วัน\n`;
  if (totals.V > 0) text += `🌴 พักร้อน (V): ${totals.V} วัน\n`;
  text += `🏝️ วันออฟรวม: ${totals.OFF} วัน\n`;
  text += `---------------------------\n`;

  state.days.forEach((day, dIdx) => {
    const code = nurse.grid[dIdx];
    const wday = state.weekdays[dIdx] || '';
    if (code && code !== '-') {
      let icon = '•';
      if (code === 'C4') icon = '☀️ [C4 เช้า 07-19]';
      else if (code === 'P4') icon = '🌙 [P4 ดึก 19-07]';
      else if (code === 'CK') icon = '⚡ [CK 16 ชม.]';
      else if (code === 'X') icon = '🏝️ [หยุดประจำสัปดาห์]';
      else if (code === 'V') icon = '🌴 [ลาพักร้อน]';
      else if (code === 'HBD') icon = '🎂 [วันเกิด]';
      else if (code === 'TRAIN') icon = '📚 [อบรม]';
      else icon = `📄 [${code}]`;

      text += `📅 ${day} (${wday}): ${icon}\n`;
    }
  });

  navigator.clipboard.writeText(text).then(() => {
    showToast('คัดลอกข้อความสรุปสำหรับส่ง LINE เรียบร้อยแล้ว! นำไปวางในแชตได้เลย');
  }).catch(() => {
    showToast('คัดลอกไม่สำเร็จ กรุณาลองใหม่อีกครั้ง', true);
  });
}


// Undo / Redo Stacks
let undoStack = [];
let redoStack = [];

function pushHistory() {
  if (state.nurses && state.nurses.length > 0) {
    const snapshot = JSON.stringify(state.nurses);
    undoStack.push(snapshot);
    if (undoStack.length > 30) undoStack.shift();
    redoStack = [];
    updateUndoRedoButtons();
  }
}

function undo() {
  if (undoStack.length === 0) return;
  const currentSnapshot = JSON.stringify(state.nurses);
  redoStack.push(currentSnapshot);
  const prevSnapshot = undoStack.pop();
  state.nurses = JSON.parse(prevSnapshot);
  renderTable();
  validateRoster();
  updateUndoRedoButtons();
  showToast('เลิกทำ (Undo) เรียบร้อย');
}

function redo() {
  if (redoStack.length === 0) return;
  const currentSnapshot = JSON.stringify(state.nurses);
  undoStack.push(currentSnapshot);
  const nextSnapshot = redoStack.pop();
  state.nurses = JSON.parse(nextSnapshot);
  renderTable();
  validateRoster();
  updateUndoRedoButtons();
  showToast('ทำซ้ำ (Redo) เรียบร้อย');
}

function updateUndoRedoButtons() {
  const btnUndo = document.getElementById('btn-undo');
  const btnRedo = document.getElementById('btn-redo');
  if (btnUndo) btnUndo.disabled = undoStack.length === 0;
  if (btnRedo) btnRedo.disabled = redoStack.length === 0;
}

// Dark Mode Toggle
function toggleDarkMode() {
  state.isDarkMode = !state.isDarkMode;
  document.body.classList.toggle('dark', state.isDarkMode);
  const icon = document.getElementById('dark-mode-icon');
  if (state.isDarkMode) {
    icon.className = 'fa-solid fa-sun text-amber-400 text-base';
    localStorage.setItem('roster_dark_mode', '1');
    showToast('เปิดโหมดกลางคืน (Dark Mode)');
  } else {
    icon.className = 'fa-solid fa-moon text-slate-500 text-base';
    localStorage.setItem('roster_dark_mode', '0');
    showToast('เปิดโหมดสว่าง (Light Mode)');
  }
}

function initDarkMode() {
  if (localStorage.getItem('roster_dark_mode') === '1') {
    state.isDarkMode = true;
    document.body.classList.add('dark');
    const icon = document.getElementById('dark-mode-icon');
    if (icon) icon.className = 'fa-solid fa-sun text-amber-400 text-base';
  }
}

// Search & Filter
function handleNurseSearch(e) {
  state.searchTerm = e.target.value.toLowerCase().trim();
  renderTableBody();
}

function setNurseFilter(type) {
  state.activeFilter = type;
  document.querySelectorAll('.filter-chip').forEach(chip => {
    const isSelected = chip.dataset.filter === type;
    chip.className = isSelected 
      ? 'filter-chip px-2.5 py-0.5 rounded-full font-semibold bg-sky-100 text-sky-800'
      : 'filter-chip px-2.5 py-0.5 rounded-full font-semibold bg-slate-100 text-slate-600 hover:bg-slate-200';
  });
  renderTableBody();
}

// Nurse Request Modal
function openRequestModal() {
  const select = document.getElementById('req-nurse-select');
  select.innerHTML = '';
  state.nurses.forEach((n, idx) => {
    const opt = document.createElement('option');
    opt.value = idx;
    opt.textContent = `${n.name} (${n.level || 'RN'})`;
    select.appendChild(opt);
  });
  document.getElementById('request-modal').classList.remove('hidden');
}

function closeRequestModal() {
  document.getElementById('request-modal').classList.add('hidden');
}

function submitNurseRequest() {
  const nIdx = parseInt(document.getElementById('req-nurse-select').value);
  const shiftType = document.getElementById('req-type-select').value;
  const startDay = parseInt(document.getElementById('req-start-day').value) || 1;
  const endDay = parseInt(document.getElementById('req-end-day').value) || 1;

  if (startDay > endDay || startDay < 1 || endDay > state.days.length) {
    showToast('ช่วงวันที่ไม่ถูกต้อง กรุณาระบุวันที่ 1 ถึง 31', true);
    return;
  }

  const nurse = state.nurses[nIdx];
  if (!nurse) return;

  pushHistory();

  for (let d = startDay - 1; d <= endDay - 1; d++) {
    nurse.grid[d] = shiftType;
    nurse.locked[d] = true;
  }

  closeRequestModal();
  renderTable();
  validateRoster();
  showToast(`บันทึกคำขอ '${shiftType}' ของ ${nurse.name} (วันที่ ${startDay}-${endDay}) พร้อมล็อกช่องแล้ว!`);
}


function highlightCrosshair(nurseIdx, dayIdx) {
  const rows = document.querySelectorAll('#roster-tbody tr');
  if (rows[nurseIdx]) rows[nurseIdx].classList.add('crosshair-row');

  // Highlight column cells
  document.querySelectorAll(`.shift-cell[data-day="${dayIdx}"]`).forEach(cell => {
    cell.classList.add('crosshair-col');
  });
}

function clearCrosshair() {
  document.querySelectorAll('.crosshair-row').forEach(el => el.classList.remove('crosshair-row'));
  document.querySelectorAll('.crosshair-col').forEach(el => el.classList.remove('crosshair-col'));
}


// Live Update Top 4 Floating Dashboard Cards
function updateDashboardCards() {
  const D = state.days.length;
  if (!state.nurses || state.nurses.length === 0) return;

  // 1. Staffing Coverage Health
  let fullyStaffedDays = 0;
  for (let d = 0; d < D; d++) {
    const dayCount = state.nurses.reduce((acc, n) => {
      const c = n.grid[d];
      return acc + (c === 'C4' || (state.rules.ck_counts_as_day && c === 'CK') ? 1 : 0);
    }, 0);
    const nightCount = state.nurses.reduce((acc, n) => {
      return acc + (n.grid[d] === 'P4' ? 1 : 0);
    }, 0);
    if (dayCount === state.rules.need_C4 && nightCount === state.rules.need_P4) {
      fullyStaffedDays++;
    }
  }

  const elStaffTitle = document.getElementById('card-staff-title');
  const elStaffSub = document.getElementById('card-staff-sub');
  if (elStaffTitle) {
    if (fullyStaffedDays === D) {
      elStaffTitle.innerHTML = `ครบ ${D}/${D} วัน (100%) <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse ml-1 inline-block"></span>`;
      elStaffSub.textContent = `เช้า ${state.rules.need_C4} คน • ดึก ${state.rules.need_P4} คน ทุกเวร`;
    } else {
      const missing = D - fullyStaffedDays;
      elStaffTitle.innerHTML = `<span class="text-rose-600 font-bold">${fullyStaffedDays}/${D} วัน (ขาด ${missing} วัน)</span>`;
      elStaffSub.textContent = `กำลังพลยังไม่ตรงเป้า ${missing} วัน (กดจัดเวรอัตโนมัติ)`;
    }
  }

  // 2. Senior RN Skill Mix
  let seniorCoveredDays = 0;
  for (let d = 0; d < D; d++) {
    let mornSr = 0, nightSr = 0;
    state.nurses.forEach(n => {
      const isSr = (n.level || '').toLowerCase().includes('senior');
      if (isSr) {
        if (n.grid[d] === 'C4' || (state.rules.ck_counts_as_day && n.grid[d] === 'CK')) mornSr++;
        if (n.grid[d] === 'P4') nightSr++;
      }
    });
    if (mornSr >= 1 && nightSr >= 1) seniorCoveredDays++;
  }

  const elSeniorTitle = document.getElementById('card-senior-title');
  const elSeniorSub = document.getElementById('card-senior-sub');
  if (elSeniorTitle) {
    const seniorCount = state.nurses.filter(n => (n.level || '').toLowerCase().includes('senior')).length;
    if (seniorCoveredDays === D) {
      elSeniorTitle.innerHTML = `Senior RN ครบทุกเวร <span class="w-2 h-2 rounded-full bg-purple-500 ml-1 inline-block"></span>`;
      elSeniorSub.textContent = `${seniorCount} ท่าน • ปลอดภัยตามเกณฑ์ 100%`;
    } else {
      elSeniorTitle.innerHTML = `<span class="text-amber-600 font-bold">${seniorCoveredDays}/${D} วัน มีพี่เลี้ยง</span>`;
      elSeniorSub.textContent = `มีบางเวรที่ยังขาด Senior RN`;
    }
  }

  // 3. Workload Fairness (Avg Hours & Disparity)
  const hoursList = state.nurses.map(n => calculateNurseTotals(n).hours);
  const avgHours = hoursList.length > 0 ? Math.round(hoursList.reduce((a, b) => a + b, 0) / hoursList.length) : 0;
  const maxHours = Math.max(...hoursList, 0);
  const minHours = Math.min(...hoursList, 0);
  const diffHours = maxHours - minHours;

  const elFairTitle = document.getElementById('card-fair-title');
  const elFairSub = document.getElementById('card-fair-sub');
  if (elFairTitle) {
    elFairTitle.textContent = `เฉลี่ย ${avgHours} ชม./คน`;
    elFairSub.textContent = `เกลี่ยสมดุล (ช่วง ${minHours}-${maxHours} ชม. ต่างกัน ±${Math.round(diffHours/2)} ชม.)`;
  }
}
