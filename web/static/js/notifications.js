// Global notification handler

class NotificationManager {
    constructor() {
        this.pollInterval = 30000; // 30 seconds
        this.updateNotificationBadge();
        this.startPolling();
    }

    startPolling() {
        // Poll for new notifications
        setInterval(() => this.updateNotificationBadge(), this.pollInterval);

        // Also update on page focus
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) {
                this.updateNotificationBadge();
            }
        });
    }

    async updateNotificationBadge() {
        try {
            const response = await fetch('/attendance/api/notifications/unread-count/', {
                headers: {
                    'X-CSRFToken': this.getCookie('csrftoken')
                }
            });

            const data = await response.json();
            this.displayBadge(data.unread_count);
        } catch (error) {
            console.error('Error updating notification badge:', error);
        }
    }

    displayBadge(count) {
        const badges = document.querySelectorAll('[data-notification-badge]');
        if (badges.length > 0) {
            badges.forEach((badge) => {
                if (count > 0) {
                    badge.textContent = count;
                    badge.style.display = 'inline-block';
                } else {
                    badge.style.display = 'none';
                }
            });
            return;
        }

        const legacyBadge = document.getElementById('notificationBadge');
        if (legacyBadge) {
            if (count > 0) {
                legacyBadge.textContent = count;
                legacyBadge.style.display = 'inline-block';
            } else {
                legacyBadge.style.display = 'none';
            }
        }
    }

    getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function () {
    window.notificationManager = new NotificationManager();

    // Toggle notification panel
    const bell = document.getElementById('notificationBell');
    const panel = document.getElementById('notificationPanel');

    if (bell && panel) {
        bell.addEventListener('click', function (e) {
            e.stopPropagation();
            panel.classList.toggle('show');
            if (panel.classList.contains('show')) {
                loadNotificationsInPanel();
            }
        });

        // Close when clicking outside
        document.addEventListener('click', function (e) {
            if (!panel.contains(e.target) && !bell.contains(e.target)) {
                panel.classList.remove('show');
            }
        });
    }
});

async function loadNotificationsInPanel() {
    try {
        const response = await fetch('/attendance/api/notifications/?limit=10', {
            headers: {
                'X-CSRFToken': getCookie('csrftoken')
            }
        });

        const data = await response.json();
        const list = document.getElementById('notificationList');

        if (list) {
            if (data.notifications.length === 0) {
                list.innerHTML = '<div class="text-center py-8 text-base-content/50">No notifications</div>';
            } else {
                list.innerHTML = data.notifications.map(n => `
                    <div class="notification-item ${!n.is_read ? 'unread' : ''}">
                        <div class="notification-icon ${n.type}">
                            ${getNotificationIcon(n.type)}
                        </div>
                        <div class="notification-content">
                            <div class="notification-title">${n.title}</div>
                            <div class="notification-message">${n.message}</div>
                            <div class="notification-time">${formatRelativeTime(n.created_at)}</div>
                        </div>
                        ${!n.is_read ? '<div class="notification-unread-dot"></div>' : ''}
                    </div>
                `).join('');
            }
        }
    } catch (error) {
        console.error('Error loading notifications:', error);
    }
}

function getNotificationIcon(type) {
    const icons = {
        'absent': '❌',
        'request_submitted': '📝',
        'request_approved': '✅',
        'request_rejected': '❌'
    };
    return icons[type] || '📢';
}

function formatRelativeTime(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);

    if (seconds < 60) return 'just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;

    return date.toLocaleDateString();
}

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

async function markAllNotificationsRead() {
    try {
        const response = await fetch('/attendance/api/notifications/read-all/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken')
            }
        });

        const data = await response.json();
        if (data.success) {
            await loadNotificationsInPanel();
            if (window.notificationManager) {
                window.notificationManager.updateNotificationBadge();
            }
        }
    } catch (error) {
        console.error('Error marking all notifications as read:', error);
    }
}