(function () {
    'use strict';

    const MOUNT_ID = 'jobportal-notification-mount';
    const STORAGE_KEY = 'jobportal_notification_read_ids';
    const REFRESH_INTERVAL_MS = 30000;
    const MAX_NOTIFICATIONS = 30;

    let notifications = [];
    let refreshTimer = null;

    function addStyles() {
        if (document.getElementById('jobportal-notification-styles')) return;
        const style = document.createElement('style');
        style.id = 'jobportal-notification-styles';
        style.textContent = `
            .jp-notification-center{position:relative;display:flex;align-items:center}
            .jp-notification-button{position:relative;width:36px;height:36px;border:1px solid #e2e8f0;border-radius:10px;background:#fff;color:#64748b;display:grid;place-items:center;cursor:pointer;transition:.18s ease}
            .jp-notification-button:hover,.jp-notification-button[aria-expanded="true"]{border-color:#bfdbfe;background:#eff6ff;color:#2563eb}
            .jp-notification-button:focus-visible{outline:3px solid rgba(37,99,235,.2);outline-offset:2px}
            .jp-notification-badge{position:absolute;top:-5px;right:-5px;min-width:18px;height:18px;padding:0 5px;border:2px solid #fff;border-radius:999px;background:#ef4444;color:#fff;display:flex;align-items:center;justify-content:center;font:800 9px/1 Inter,Arial,sans-serif}
            .jp-notification-badge[hidden]{display:none}
            .jp-notification-panel{position:absolute;right:0;top:44px;width:370px;max-width:calc(100vw - 28px);z-index:90;overflow:hidden;border:1px solid #e2e8f0;border-radius:16px;background:#fff;box-shadow:0 20px 50px rgba(15,23,42,.18);font-family:Inter,Arial,sans-serif}
            .jp-notification-panel[hidden]{display:none}
            .jp-notification-header{height:58px;padding:0 16px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #eef2f7}
            .jp-notification-title{margin:0;color:#0f172a;font-size:14px;font-weight:800}
            .jp-notification-mark-all{border:0;background:transparent;color:#2563eb;font-size:11px;font-weight:750;cursor:pointer;padding:7px;border-radius:7px}
            .jp-notification-mark-all:hover{background:#eff6ff}
            .jp-notification-list{max-height:360px;overflow-y:auto}
            .jp-notification-item{position:relative;width:100%;padding:14px 16px;border:0;border-bottom:1px solid #f1f5f9;background:#fff;display:grid;grid-template-columns:36px minmax(0,1fr);gap:11px;text-align:left;cursor:pointer;transition:.15s ease}
            .jp-notification-item:hover{background:#f8fafc}
            .jp-notification-item.jp-unread{background:#f8fbff}
            .jp-notification-item.jp-unread:hover{background:#eff6ff}
            .jp-notification-icon{width:36px;height:36px;border-radius:10px;display:grid;place-items:center;font-size:13px;font-weight:850}
            .jp-tone-blue{background:#eff6ff;color:#2563eb}.jp-tone-green{background:#ecfdf5;color:#059669}.jp-tone-amber{background:#fffbeb;color:#d97706}.jp-tone-red{background:#fff1f2;color:#e11d48}.jp-tone-slate{background:#f1f5f9;color:#64748b}
            .jp-notification-copy{min-width:0}
            .jp-notification-row{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
            .jp-notification-item-title{margin:0;color:#0f172a;font-size:12px;font-weight:800;line-height:1.4}
            .jp-notification-dot{width:7px;height:7px;flex:0 0 7px;margin-top:5px;border-radius:50%;background:#2563eb}
            .jp-notification-message{margin:3px 0 0;color:#64748b;font-size:11px;line-height:1.55;overflow-wrap:anywhere}
            .jp-notification-time{margin:6px 0 0;color:#94a3b8;font-size:10px;font-weight:600}
            .jp-notification-empty{padding:42px 24px;text-align:center;color:#94a3b8}
            .jp-notification-empty-icon{width:42px;height:42px;margin:0 auto 10px;border-radius:13px;background:#f1f5f9;color:#94a3b8;display:grid;place-items:center}
            .jp-notification-empty-title{margin:0;color:#475569;font-size:12px;font-weight:800}
            .jp-notification-empty-copy{margin:5px 0 0;font-size:11px;line-height:1.5}
            .jp-notification-footer{padding:10px;border-top:1px solid #eef2f7;background:#f8fafc}
            .jp-notification-dashboard{width:100%;padding:9px 12px;border:1px solid #dbeafe;border-radius:9px;background:#fff;color:#2563eb;font-size:11px;font-weight:800;cursor:pointer}
            .jp-notification-dashboard:hover{background:#eff6ff}
            @media(max-width:520px){.jp-notification-panel{position:fixed;top:66px;right:14px;left:14px;width:auto;max-width:none}}
        `;
        document.head.appendChild(style);
    }

    function bellIcon() {
        return '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9Z"/><path d="M10 21h4"/></svg>';
    }

    function emptyBellIcon() {
        return '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9Z"/><path d="M10 21h4"/></svg>';
    }

    function createInterface(mount) {
        mount.innerHTML = `
            <div class="jp-notification-center">
                <button type="button" id="jp-notification-button" class="jp-notification-button" aria-label="Open notifications" aria-haspopup="true" aria-expanded="false">
                    ${bellIcon()}
                    <span id="jp-notification-badge" class="jp-notification-badge" hidden>0</span>
                </button>
                <section id="jp-notification-panel" class="jp-notification-panel" aria-label="Notifications" hidden>
                    <header class="jp-notification-header">
                        <h2 class="jp-notification-title">Notifications</h2>
                        <button type="button" id="jp-notification-mark-all" class="jp-notification-mark-all">Mark all as read</button>
                    </header>
                    <div id="jp-notification-list" class="jp-notification-list"></div>
                    <footer class="jp-notification-footer">
                        <button type="button" id="jp-notification-dashboard" class="jp-notification-dashboard">View applications</button>
                    </footer>
                </section>
            </div>
        `;

        const button = document.getElementById('jp-notification-button');
        const panel = document.getElementById('jp-notification-panel');
        const markAll = document.getElementById('jp-notification-mark-all');
        const dashboard = document.getElementById('jp-notification-dashboard');

        button.addEventListener('click', function (event) {
            event.stopPropagation();
            const willOpen = panel.hidden;
            panel.hidden = !willOpen;
            button.setAttribute('aria-expanded', String(willOpen));
        });
        panel.addEventListener('click', function (event) {
            event.stopPropagation();
        });
        markAll.addEventListener('click', markAllAsRead);
        dashboard.addEventListener('click', function () {
            window.location.href = '/dashboard';
        });
        document.addEventListener('click', closePanel);
        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') closePanel();
        });
    }

    function closePanel() {
        const panel = document.getElementById('jp-notification-panel');
        const button = document.getElementById('jp-notification-button');
        if (panel) panel.hidden = true;
        if (button) button.setAttribute('aria-expanded', 'false');
    }

    function getReadIds() {
        try {
            const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
            return new Set(Array.isArray(stored) ? stored.map(String) : []);
        } catch (_) {
            return new Set();
        }
    }

    function saveReadIds(readIds) {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(readIds).slice(-500)));
    }

    function markAsRead(notificationId) {
        const readIds = getReadIds();
        readIds.add(String(notificationId));
        saveReadIds(readIds);
        renderNotifications();
    }

    function markAllAsRead() {
        const readIds = getReadIds();
        notifications.forEach(function (item) {
            readIds.add(item.id);
        });
        saveReadIds(readIds);
        renderNotifications();
    }

    function normaliseDate(value) {
        if (!value) return null;
        const parsed = new Date(value);
        return Number.isNaN(parsed.getTime()) ? null : parsed;
    }

    function displayDate(value, includeTime) {
        const date = normaliseDate(value);
        if (!date) return '';
        const options = includeTime
            ? {day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'}
            : {day: 'numeric', month: 'short', year: 'numeric'};
        return new Intl.DateTimeFormat('en-MY', options).format(date);
    }

    function statusTone(status) {
        const value = String(status || '').toLowerCase();
        if (value === 'offer' || value === 'accepted' || value === 'hired') return {tone: 'green', icon: '✓'};
        if (value === 'interview') return {tone: 'blue', icon: 'I'};
        if (value === 'rejected' || value === 'withdrawn') return {tone: 'red', icon: '!'};
        if (value === 'reviewing' || value === 'reviewed' || value === 'shortlisted') return {tone: 'amber', icon: '•'};
        return {tone: 'slate', icon: '•'};
    }

    function titleCase(value) {
        return String(value || '')
            .replace(/[_-]+/g, ' ')
            .replace(/\b\w/g, function (letter) { return letter.toUpperCase(); });
    }

    function buildNotifications(applications) {
        const result = [];
        (Array.isArray(applications) ? applications : []).forEach(function (application) {
            const applicationId = String(application.id || application.jobId || 'application');
            const job = String(application.job || application.position || 'your application');
            const company = String(application.company || 'the employer');
            const appliedAt = application.date || application.appliedAt || application.created_at || '';

            result.push({
                id: `${applicationId}:submitted`,
                title: 'Application submitted',
                message: `${job} at ${company}`,
                timestamp: normaliseDate(appliedAt)?.getTime() || 0,
                timeLabel: displayDate(appliedAt, false),
                tone: 'slate',
                icon: '✓'
            });

            const status = String(application.status || 'Pending');
            if (status.toLowerCase() !== 'pending') {
                const style = statusTone(status);
                result.push({
                    id: `${applicationId}:status:${status.toLowerCase()}`,
                    title: `Application ${titleCase(status)}`,
                    message: `${job} at ${company}`,
                    timestamp: normaliseDate(application.updatedAt || application.updated_at || appliedAt)?.getTime() || 0,
                    timeLabel: displayDate(application.updatedAt || application.updated_at || appliedAt, false),
                    tone: style.tone,
                    icon: style.icon
                });
            }

            const interview = application.interview;
            if (interview && interview.interviewAt) {
                const interviewDate = displayDate(interview.interviewAt, true);
                const meeting = String(interview.locationOrLink || '').trim();
                const interviewType = titleCase(interview.interviewType || 'Interview');
                result.push({
                    id: `${applicationId}:interview:${interview.interviewAt}:${meeting}`,
                    title: 'Interview scheduled',
                    message: `${job} · ${interviewDate}${meeting ? ` · ${interviewType}: ${meeting}` : ''}`,
                    timestamp: normaliseDate(interview.interviewAt)?.getTime() || 0,
                    timeLabel: interviewDate,
                    tone: 'blue',
                    icon: 'I'
                });
            }
        });

        const unique = new Map();
        result.forEach(function (item) { unique.set(item.id, item); });
        return Array.from(unique.values())
            .sort(function (a, b) { return b.timestamp - a.timestamp; })
            .slice(0, MAX_NOTIFICATIONS);
    }

    function createNotificationElement(item, isUnread) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = `jp-notification-item${isUnread ? ' jp-unread' : ''}`;
        button.setAttribute('aria-label', `${item.title}: ${item.message}`);

        const icon = document.createElement('span');
        icon.className = `jp-notification-icon jp-tone-${item.tone}`;
        icon.textContent = item.icon;

        const copy = document.createElement('span');
        copy.className = 'jp-notification-copy';
        const headingRow = document.createElement('span');
        headingRow.className = 'jp-notification-row';
        const title = document.createElement('span');
        title.className = 'jp-notification-item-title';
        title.textContent = item.title;
        headingRow.appendChild(title);
        if (isUnread) {
            const dot = document.createElement('span');
            dot.className = 'jp-notification-dot';
            dot.setAttribute('aria-label', 'Unread');
            headingRow.appendChild(dot);
        }
        const message = document.createElement('span');
        message.className = 'jp-notification-message';
        message.textContent = item.message;
        const time = document.createElement('span');
        time.className = 'jp-notification-time';
        time.textContent = item.timeLabel || 'Application update';
        copy.append(headingRow, message, time);
        button.append(icon, copy);
        button.addEventListener('click', function () {
            markAsRead(item.id);
            window.location.href = '/dashboard';
        });
        return button;
    }

    function renderNotifications() {
        const list = document.getElementById('jp-notification-list');
        const badge = document.getElementById('jp-notification-badge');
        const markAll = document.getElementById('jp-notification-mark-all');
        if (!list || !badge || !markAll) return;

        const readIds = getReadIds();
        const unreadCount = notifications.filter(function (item) {
            return !readIds.has(item.id);
        }).length;
        badge.hidden = unreadCount === 0;
        badge.textContent = unreadCount > 9 ? '9+' : String(unreadCount);
        markAll.disabled = unreadCount === 0;
        markAll.style.opacity = unreadCount === 0 ? '.45' : '1';

        list.replaceChildren();
        if (!notifications.length) {
            const empty = document.createElement('div');
            empty.className = 'jp-notification-empty';
            empty.innerHTML = `<div class="jp-notification-empty-icon">${emptyBellIcon()}</div><p class="jp-notification-empty-title">No notifications yet</p><p class="jp-notification-empty-copy">Application and interview updates will appear here.</p>`;
            list.appendChild(empty);
            return;
        }
        notifications.forEach(function (item) {
            list.appendChild(createNotificationElement(item, !readIds.has(item.id)));
        });
    }

    async function refreshNotifications() {
        try {
            const response = await fetch('/api/applications', {
                headers: {'Accept': 'application/json'},
                cache: 'no-store'
            });
            if (response.status === 401) return;
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Unable to load notifications.');
            notifications = buildNotifications(data);
            renderNotifications();
        } catch (error) {
            console.warn('Notification refresh failed:', error);
        }
    }

    function initialise() {
        const mount = document.getElementById(MOUNT_ID);
        if (!mount) return;
        addStyles();
        createInterface(mount);
        renderNotifications();
        refreshNotifications();
        refreshTimer = window.setInterval(refreshNotifications, REFRESH_INTERVAL_MS);
        window.addEventListener('storage', function (event) {
            if (event.key === STORAGE_KEY) renderNotifications();
        });
        window.addEventListener('beforeunload', function () {
            if (refreshTimer) window.clearInterval(refreshTimer);
        }, {once: true});
    }

    window.JobPortalNotifications = {refresh: refreshNotifications};
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialise, {once: true});
    } else {
        initialise();
    }
}());