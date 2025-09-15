// Main JavaScript file for Pamoja Agencies SHG

document.addEventListener('DOMContentLoaded', function() {
    try {
        // Initialize all components safely
        initializeTooltips();
        initializeAlerts();
        initializeFormValidation();
        initializeFileUpload();
        initializeDataTables();
        initializeConfirmations();
        initializeCurrencyFormatting();
        initializeCharts();

        // Fix voting date inputs
        initializeDateTimeInputs();

        // Fix delete functionality
        initializeDeleteButtons();

        // Service worker temporarily disabled to fix reconnection issues
        // if ('serviceWorker' in navigator) {
        //     navigator.serviceWorker.register('/static/sw.js')
        //         .then(registration => console.log('SW registered'))
        //         .catch(error => console.log('SW registration failed'));
        // }
    } catch (error) {
        console.warn('Initialization error:', error);
    }
});

// Initialize date-time inputs for voting
function initializeDateTimeInputs() {
    const dateInputs = document.querySelectorAll('input[type="datetime-local"]');
    dateInputs.forEach(input => {
        // Set minimum date to now
        const now = new Date();
        const isoString = now.toISOString().slice(0, 16);
        input.min = isoString;

        // Format existing values
        if (input.value && !input.value.includes('T')) {
            try {
                const date = new Date(input.value);
                input.value = date.toISOString().slice(0, 16);
            } catch (e) {
                console.warn('Date formatting error:', e);
            }
        }
    });
}

// Fix delete button functionality
function initializeDeleteButtons() {
    const deleteButtons = document.querySelectorAll('[data-bs-toggle="modal"][data-bs-target*="delete"]');
    deleteButtons.forEach(button => {
        if (!button.hasEventListener) {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                const targetModal = document.querySelector(this.getAttribute('data-bs-target'));
                if (targetModal) {
                    const modal = new bootstrap.Modal(targetModal);
                    modal.show();
                }
            });
            button.hasEventListener = true;
        }
    });
}

// Initialize Bootstrap tooltips
function initializeTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// Auto-dismiss alerts after 5 seconds (but not debt reminders)
function initializeAlerts() {
    const alerts = document.querySelectorAll('.alert:not(.alert-permanent):not(.debt-reminder)');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
}

// Form validation enhancements
function initializeFormValidation() {
    const forms = document.querySelectorAll('.needs-validation');

    forms.forEach(form => {
        form.addEventListener('submit', function(event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        });
    });

    // Real-time validation for password confirmation
    const passwordField = document.getElementById('new_password');
    const confirmPasswordField = document.getElementById('confirm_password');

    if (passwordField && confirmPasswordField) {
        confirmPasswordField.addEventListener('input', function() {
            if (passwordField.value !== this.value) {
                this.setCustomValidity('Passwords do not match');
                this.classList.add('is-invalid');
            } else {
                this.setCustomValidity('');
                this.classList.remove('is-invalid');
                this.classList.add('is-valid');
            }
        });
    }
}

// File upload enhancements
function initializeFileUpload() {
    const fileInputs = document.querySelectorAll('input[type="file"]');

    fileInputs.forEach(input => {
        const container = input.closest('.mb-3') || input.parentElement;

        // Create drag and drop area
        if (!container.querySelector('.file-upload-area')) {
            const uploadArea = document.createElement('div');
            uploadArea.className = 'file-upload-area mt-2';
            uploadArea.innerHTML = `
                <i class="fas fa-cloud-upload-alt fa-2x text-muted mb-2"></i>
                <p class="text-muted mb-0">Drag and drop files here or click to browse</p>
            `;

            uploadArea.addEventListener('click', () => input.click());

            // Drag and drop functionality
            uploadArea.addEventListener('dragover', function(e) {
                e.preventDefault();
                this.classList.add('dragover');
            });

            uploadArea.addEventListener('dragleave', function(e) {
                e.preventDefault();
                this.classList.remove('dragover');
            });

            uploadArea.addEventListener('drop', function(e) {
                e.preventDefault();
                this.classList.remove('dragover');

                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    input.files = files;
                    updateFileInfo(input, files[0]);
                }
            });

            container.appendChild(uploadArea);
        }

        // File selection handler
        input.addEventListener('change', function() {
            if (this.files.length > 0) {
                updateFileInfo(this, this.files[0]);
            }
        });
    });
}

// Update file information display
function updateFileInfo(input, file) {
    const container = input.closest('.mb-3') || input.parentElement;
    let fileInfo = container.querySelector('.file-info');

    if (!fileInfo) {
        fileInfo = document.createElement('div');
        fileInfo.className = 'file-info mt-2';
        container.appendChild(fileInfo);
    }

    const fileSize = (file.size / 1024 / 1024).toFixed(2);
    fileInfo.innerHTML = `
        <div class="alert alert-info">
            <i class="fas fa-file me-2"></i>
            <strong>${file.name}</strong> (${fileSize} MB)
        </div>
    `;
}

// Initialize data tables for better UX
function initializeDataTables() {
    const tables = document.querySelectorAll('.table');

    tables.forEach(table => {
        // Add search functionality for large tables
        if (table.rows.length > 10) {
            addTableSearch(table);
        }

        // Add sorting functionality
        addTableSort(table);
    });
}

// Add search functionality to tables
function addTableSearch(table) {
    const container = table.closest('.table-responsive') || table.parentElement;

    if (!container.querySelector('.table-search')) {
        const searchContainer = document.createElement('div');
        searchContainer.className = 'table-search mb-3';
        searchContainer.innerHTML = `
            <div class="row align-items-center">
                <div class="col-md-6">
                    <input type="text" class="form-control" placeholder="Search table..." />
                </div>
                <div class="col-md-6 text-md-end">
                    <small class="text-muted">Showing <span class="visible-rows">${table.rows.length - 1}</span> of ${table.rows.length - 1} entries</small>
                </div>
            </div>
        `;

        container.insertBefore(searchContainer, table.parentElement);

        const searchInput = searchContainer.querySelector('input');
        const visibleRowsSpan = searchContainer.querySelector('.visible-rows');

        searchInput.addEventListener('input', function() {
            const searchTerm = this.value.toLowerCase();
            const rows = table.querySelectorAll('tbody tr');
            let visibleCount = 0;

            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                if (text.includes(searchTerm)) {
                    row.style.display = '';
                    visibleCount++;
                } else {
                    row.style.display = 'none';
                }
            });

            visibleRowsSpan.textContent = visibleCount;
        });
    }
}

// Add sorting functionality to tables
function addTableSort(table) {
    const headers = table.querySelectorAll('th');

    headers.forEach((header, index) => {
        header.style.cursor = 'pointer';
        header.innerHTML += ' <i class="fas fa-sort text-muted ms-1"></i>';

        header.addEventListener('click', function() {
            sortTable(table, index);
        });
    });
}

// Sort table by column
function sortTable(table, columnIndex) {
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const header = table.querySelectorAll('th')[columnIndex];
    const sortIcon = header.querySelector('i');

    // Reset all sort icons
    table.querySelectorAll('th i').forEach(icon => {
        icon.className = 'fas fa-sort text-muted ms-1';
    });

    // Determine sort direction
    const isAscending = !header.classList.contains('sort-asc');
    header.classList.toggle('sort-asc', isAscending);
    header.classList.toggle('sort-desc', !isAscending);

    // Update sort icon
    sortIcon.className = `fas fa-sort-${isAscending ? 'up' : 'down'} text-primary ms-1`;

    // Sort rows
    rows.sort((a, b) => {
        const aValue = a.cells[columnIndex].textContent.trim();
        const bValue = b.cells[columnIndex].textContent.trim();

        // Try to parse as numbers
        const aNum = parseFloat(aValue.replace(/[^\d.-]/g, ''));
        const bNum = parseFloat(bValue.replace(/[^\d.-]/g, ''));

        if (!isNaN(aNum) && !isNaN(bNum)) {
            return isAscending ? aNum - bNum : bNum - aNum;
        }

        // Sort as strings
        return isAscending ? aValue.localeCompare(bValue) : bValue.localeCompare(aValue);
    });

    // Reorder rows in DOM
    rows.forEach(row => tbody.appendChild(row));
}

// Initialize confirmation dialogs
function initializeConfirmations() {
    const confirmLinks = document.querySelectorAll('[data-confirm]');

    confirmLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            const message = this.getAttribute('data-confirm');
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });
}

// Currency formatting
function initializeCurrencyFormatting() {
    const currencyElements = document.querySelectorAll('.currency');

    currencyElements.forEach(element => {
        const value = parseFloat(element.textContent.replace(/[^\d.-]/g, ''));
        if (!isNaN(value)) {
            element.textContent = formatCurrency(value);
        }
    });
}

// Format currency helper function
function formatCurrency(amount) {
    if (isNaN(amount)) return 'KSh 0.00';
    return 'KSh ' + parseFloat(amount).toLocaleString('en-KE', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

// Initialize charts
function initializeCharts() {
    // Set Chart.js defaults
    if (typeof Chart !== 'undefined') {
        Chart.defaults.responsive = true;
        Chart.defaults.maintainAspectRatio = false;
        Chart.defaults.plugins.legend.position = 'bottom';
        Chart.defaults.scales.linear.beginAtZero = true;
    }
}

// Utility functions
const Utils = {
    // Show loading state
    showLoading: function(element) {
        element.classList.add('loading');
        element.style.pointerEvents = 'none';
    },

    // Hide loading state
    hideLoading: function(element) {
        element.classList.remove('loading');
        element.style.pointerEvents = '';
    },

    // Show toast notification
    showToast: function(message, type = 'info') {
        const toastContainer = document.getElementById('toast-container') || this.createToastContainer();

        const toast = document.createElement('div');
        toast.className = `toast align-items-center text-white bg-${type} border-0`;
        toast.setAttribute('role', 'alert');
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;

        toastContainer.appendChild(toast);

        const bsToast = new bootstrap.Toast(toast);
        bsToast.show();

        // Remove toast element after it's hidden
        toast.addEventListener('hidden.bs.toast', () => {
            toast.remove();
        });
    },

    // Create toast container if it doesn't exist
    createToastContainer: function() {
        const container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container position-fixed top-0 end-0 p-3';
        document.body.appendChild(container);
        return container;
    },

    // Validate form data
    validateForm: function(formElement) {
        const inputs = formElement.querySelectorAll('input[required], select[required], textarea[required]');
        let isValid = true;

        inputs.forEach(input => {
            if (!input.value.trim()) {
                input.classList.add('is-invalid');
                isValid = false;
            } else {
                input.classList.remove('is-invalid');
                input.classList.add('is-valid');
            }
        });

        return isValid;
    },

    // Format file size
    formatFileSize: function(bytes) {
        if (bytes === 0) return '0 Bytes';

        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));

        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },

    // Debounce function
    debounce: function(func, wait, immediate) {
        let timeout;
        return function executedFunction() {
            const context = this;
            const args = arguments;

            const later = function() {
                timeout = null;
                if (!immediate) func.apply(context, args);
            };

            const callNow = immediate && !timeout;
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);

            if (callNow) func.apply(context, args);
        };
    }
};

// Export utilities for use in other scripts
window.PamojaUtils = Utils;

// Handle form submissions with loading states
document.addEventListener('submit', function(e) {
    const form = e.target;
    const submitBtn = form.querySelector('button[type="submit"]');

    if (submitBtn) {
        Utils.showLoading(submitBtn);

        // Re-enable button after 5 seconds to prevent indefinite loading
        setTimeout(() => {
            Utils.hideLoading(submitBtn);
        }, 5000);
    }
});

// Handle AJAX requests (if any)
window.addEventListener('beforeunload', function() {
    // Clean up any ongoing operations
    document.querySelectorAll('.loading').forEach(element => {
        Utils.hideLoading(element);
    });
});

// Print functionality
function printPage() {
    window.print();
}

// Export data functionality
function exportData(format, data, filename) {
    let content, mimeType, extension;

    switch (format) {
        case 'csv':
            content = convertToCSV(data);
            mimeType = 'text/csv';
            extension = 'csv';
            break;
        case 'json':
            content = JSON.stringify(data, null, 2);
            mimeType = 'application/json';
            extension = 'json';
            break;
        default:
            console.error('Unsupported export format:', format);
            return;
    }

    const blob = new Blob([content], { type: mimeType });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${filename}.${extension}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
}

// Convert data to CSV format
function convertToCSV(data) {
    if (!Array.isArray(data) || data.length === 0) {
        return '';
    }

    const headers = Object.keys(data[0]);
    const csvContent = [
        headers.join(','),
        ...data.map(row => 
            headers.map(header => 
                JSON.stringify(row[header] || '')
            ).join(',')
        )
    ].join('\n');

    return csvContent;
}

// Enhanced debt reminder functionality
function showDebtReminders() {
    const debtElements = document.querySelectorAll('.debt-reminder');
    debtElements.forEach(element => {
        // Ensure reminders are visible and persistent
        element.style.display = 'block';
        element.style.animation = 'debtPulse 3s infinite';
        element.classList.add('persistent-reminder', 'alert-permanent');

        // Remove any alert-dismissible classes that might auto-hide the reminder
        element.classList.remove('alert-dismissible', 'fade');

        // Remove any existing close buttons that might dismiss the reminder
        const existingCloseBtn = element.querySelector('.btn-close');
        if (existingCloseBtn) {
            existingCloseBtn.remove();
        }

        // Add action buttons if not already present
        if (!element.querySelector('.reminder-actions')) {
            const actionsDiv = document.createElement('div');
            actionsDiv.className = 'reminder-actions mt-2';
            actionsDiv.innerHTML = `
                <button class="btn btn-sm btn-success me-2" onclick="markAsPaid(this)" data-type="${element.dataset.type}" data-id="${element.dataset.id}">
                    <i class="fas fa-check"></i> Mark as Paid
                </button>
                <button class="btn btn-sm btn-warning me-2" onclick="snoozeReminder(this)">
                    <i class="fas fa-clock"></i> Snooze (1 day)
                </button>
                <button class="btn btn-sm btn-secondary" onclick="dismissReminder(this)">
                    <i class="fas fa-times"></i> Dismiss
                </button>
            `;
            element.appendChild(actionsDiv);
        }

        // Add a more prominent visual indicator
        element.style.position = 'relative';
        element.style.zIndex = '1000';
        element.style.marginBottom = '1rem';
        element.style.boxShadow = '0 4px 8px rgba(0, 0, 0, 0.2)';
    });
}

function markAsPaid(button) {
    const reminder = button.closest('.debt-reminder');
    const type = button.dataset.type;
    const id = button.dataset.id;

    if (confirm('Are you sure you want to mark this as paid?')) {
        // Here you would typically make an API call to update the payment status
        showNotification(`${type} marked as paid. Please wait for admin approval.`, 'success');
        reminder.style.display = 'none';

        // Store in localStorage that this was marked as paid
        const paidItems = JSON.parse(localStorage.getItem('markedAsPaid') || '[]');
        paidItems.push({type, id, date: new Date().toISOString()});
        localStorage.setItem('markedAsPaid', JSON.stringify(paidItems));
    }
}

function snoozeReminder(button) {
    const reminder = button.closest('.debt-reminder');
    const snoozeUntil = new Date();
    snoozeUntil.setDate(snoozeUntil.getDate() + 1);

    reminder.style.display = 'none';
    showNotification('Reminder snoozed for 1 day', 'info');

    // Store snooze info
    const snoozedItems = JSON.parse(localStorage.getItem('snoozedReminders') || '[]');
    snoozedItems.push({
        id: reminder.dataset.id,
        type: reminder.dataset.type,
        snoozeUntil: snoozeUntil.toISOString()
    });
    localStorage.setItem('snoozedReminders', JSON.stringify(snoozedItems));

    // Set timeout to show reminder again
    setTimeout(() => {
        reminder.style.display = 'block';
        showNotification('Payment reminder is back!', 'warning');
    }, 24 * 60 * 60 * 1000); // 24 hours
}

function dismissReminder(button) {
    const reminder = button.closest('.debt-reminder');
    reminder.style.display = 'none';
    showNotification('Reminder dismissed', 'info');
}

// Check for snoozed reminders on page load
function checkSnoozedReminders() {
    const snoozedItems = JSON.parse(localStorage.getItem('snoozedReminders') || '[]');
    const now = new Date();

    snoozedItems.forEach(item => {
        if (new Date(item.snoozeUntil) <= now) {
            const reminder = document.querySelector(`[data-id="${item.id}"][data-type="${item.type}"]`);
            if (reminder) {
                reminder.style.display = 'block';
                showNotification(`${item.type} reminder is back!`, 'warning');
            }
        }
    });

    // Remove expired snoozes
    const activeSnoozes = snoozedItems.filter(item => new Date(item.snoozeUntil) > now);
    localStorage.setItem('snoozedReminders', JSON.stringify(activeSnoozes));
}

// Loan modal fixes
function fixLoanModals() {
    const loanModals = document.querySelectorAll('[id^="deleteLoanModal"]');
    loanModals.forEach(modal => {
        const modalInstance = new bootstrap.Modal(modal);

        // Fix modal backdrop issues
        modal.addEventListener('hidden.bs.modal', function () {
            document.body.classList.remove('modal-open');
            const backdrop = document.querySelector('.modal-backdrop');
            if (backdrop) backdrop.remove();
        });

        // Ensure proper form submission
        const form = modal.querySelector('form');
        if (form) {
            form.addEventListener('submit', function(e) {
                const reason = form.querySelector('textarea[name="reason"]');
                if (!reason.value.trim()) {
                    e.preventDefault();
                    alert('Please provide a reason for deletion');
                    return false;
                }
            });
        }
    });
}

// Offline data sync
let offlineData = {};

function syncOfflineData() {
    // Only sync for authenticated users
    const userInfo = document.querySelector('[data-user-id]') || document.querySelector('.navbar-nav');
    if (!userInfo) {
        return;
    }

    // Load cached data first
    try {
        offlineData = JSON.parse(localStorage.getItem('offlineData') || '{}');
    } catch (e) {
        offlineData = {};
    }

    if (!navigator.onLine) {
        loadOfflineData();
        return;
    }

    // Simplified sync with timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000); // 3 second timeout

    fetch('/offline-sync', {
        signal: controller.signal,
        method: 'GET',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => {
        clearTimeout(timeoutId);
        if (response.ok) {
            return response.json();
        }
        throw new Error('Sync failed');
    })
    .then(data => {
        if (data && data.success && data.data) {
            offlineData = data.data;
            localStorage.setItem('offlineData', JSON.stringify(data.data));
        }
    })
    .catch(error => {
        // Silently fail and use cached data
        loadOfflineData();
    });
}

// Load offline data on page load
function loadOfflineData() {
    offlineData = JSON.parse(localStorage.getItem('offlineData') || '{}');
}

function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show position-fixed`;
    notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    document.body.appendChild(notification);

    // Auto remove after 5 seconds
    setTimeout(() => {
        if (notification && notification.parentNode) {
            notification.remove();
        }
    }, 5000);
}

// Badge and points animation
function animateBadges() {
    const badges = document.querySelectorAll('.badge-earned');
    badges.forEach((badge, index) => {
        setTimeout(() => {
            badge.style.animation = 'bounceIn 0.5s ease-out';
        }, index * 200);
    });
}

// Gamification notifications
function showAchievementNotification(badge, points) {
    const notification = document.createElement('div');
    notification.className = 'achievement-notification position-fixed top-0 end-0 m-3 p-3 bg-warning text-dark rounded shadow';
    notification.innerHTML = `
        <div class="d-flex align-items-center">
            <i class="fas fa-trophy fa-2x me-3"></i>
            <div>
                <h6 class="mb-0">Achievement Unlocked!</h6>
                <small>${badge} (+${points} points)</small>
            </div>
        </div>
    `;

    document.body.appendChild(notification);

    setTimeout(() => {
        notification.remove();
    }, 5000);
}

// PWA Install functionality
let deferredPrompt;

// PWA install prompt
window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;

    // Show install button
    const installBtn = document.getElementById('installBtn');
    if (installBtn) {
        installBtn.style.display = 'block';
    }
});

function installPWA() {
    if (deferredPrompt) {
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then((choiceResult) => {
            if (choiceResult.outcome === 'accepted') {
                showNotification('App installed successfully!', 'success');
            }
            deferredPrompt = null;
        });
    }
}

// Share functionality
function shareApp() {
    if (navigator.share) {
        navigator.share({
            title: 'Pamoja Agencies SHG',
            text: 'Join our Self-Help Group management platform',
            url: window.location.origin
        }).then(() => {
            showNotification('App shared successfully!', 'success');
        }).catch(() => {
            copyToClipboard();
        });
    } else {
        copyToClipboard();
    }
}

function copyToClipboard() {
    const url = window.location.origin;
    if (navigator.clipboard) {
        navigator.clipboard.writeText(url).then(() => {
            showNotification('App link copied to clipboard!', 'info');
        }).catch(() => {
            fallbackCopyToClipboard(url);
        });
    } else {
        fallbackCopyToClipboard(url);
    }
}

function fallbackCopyToClipboard(text) {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.left = '-999999px';
    textArea.style.top = '-999999px';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
        document.execCommand('copy');
        showNotification('App link copied to clipboard!', 'info');
    } catch (err) {
        showNotification('Could not copy link. Please copy manually: ' + text, 'warning');
    }
    document.body.removeChild(textArea);
}

// Check if app is already installed
window.addEventListener('appinstalled', () => {
    showNotification('App installed successfully!', 'success');
    const installBtn = document.getElementById('installBtn');
    if (installBtn) {
        installBtn.style.display = 'none';
    }
});

// Generate full backup
function generateFullBackup() {
    showNotification('Generating backup...', 'info');
    
    fetch('/reports/export/csv')
        .then(response => response.blob())
        .then(blob => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `pamoja_backup_${new Date().toISOString().split('T')[0]}.csv`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
            showNotification('Backup downloaded successfully!', 'success');
        })
        .catch(error => {
            console.error('Backup error:', error);
            showNotification('Backup failed. Please try again.', 'error');
        });
}

// Export all data as JSON
function exportAllData() {
    showNotification('Exporting data...', 'info');
    
    // Collect offline data if available
    const exportData = {
        timestamp: new Date().toISOString(),
        offline_data: offlineData,
        app_version: '1.0.0'
    };
    
    const dataStr = JSON.stringify(exportData, null, 2);
    const blob = new Blob([dataStr], { type: 'application/json' });
    const url = window.URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = `pamoja_data_export_${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
    
    showNotification('Data exported successfully!', 'success');
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Initialize all components
    initializeTooltips();
    initializeAlerts();
    initializeFormValidation();
    initializeFileUpload();
    initializeDataTables();
    initializeConfirmations();
    initializeCurrencyFormatting();
    initializeCharts();

    // Debt reminders and loan modals
    showDebtReminders();
    fixLoanModals();

    // Gamification
    animateBadges();
    // showAchievementNotification('First Loan', 100); // Example notification

    // Offline and sync
    loadOfflineData();
    checkSnoozedReminders();

    // Auto-sync offline data every 15 minutes if online (reduced frequency for better performance)
    const userInfo = document.querySelector('[data-user-id]') || document.querySelector('.navbar-nav');
    if (userInfo) {
        if (navigator.onLine) {
            // Initial sync with delay to avoid blocking page load
            setTimeout(syncOfflineData, 2000);
            // Reduced sync frequency for better performance
            setInterval(syncOfflineData, 15 * 60 * 1000);
        }
    }

    // Initialize section classes for gradients
    initializeSectionClasses();

    // Initialize relative time displays
    initializeRelativeTime();

    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
});

// Membership application approval
function approveApplication(appId, action) {
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = `/membership-applications/${appId}/review`;

    // Add CSRF token
    const csrfInput = document.createElement('input');
    csrfInput.type = 'hidden';
    csrfInput.name = 'csrf_token';
    csrfInput.value = document.querySelector('meta[name="csrf-token"]')?.content || '';
    form.appendChild(csrfInput);

    // Add action input
    const actionInput = document.createElement('input');
    actionInput.type = 'hidden';
    actionInput.name = 'action';
    actionInput.value = action;
    form.appendChild(actionInput);

    // Add rejection reason if rejecting
    if (action === 'reject') {
        const reason = prompt('Please provide a reason for rejection:');
        if (!reason) return;

        const reasonInput = document.createElement('input');
        reasonInput.type = 'hidden';
        reasonInput.name = 'rejection_reason';
        reasonInput.value = reason;
        form.appendChild(reasonInput);
    }

    document.body.appendChild(form);
    form.submit();
}

// Initialize section classes for gradients
function initializeSectionClasses() {
    // Add section classes based on page content
    const path = window.location.pathname;
    const body = document.body;

    if (path.includes('members')) {
        body.classList.add('members-section');
    } else if (path.includes('loans')) {
        body.classList.add('loans-section');
    } else if (path.includes('contributions')) {
        body.classList.add('contributions-section');
    } else if (path.includes('announcements') || path.includes('meetings')) {
        body.classList.add('announcements-section');
    } else if (path.includes('fines')) {
        body.classList.add('fines-section');
    } else if (path.includes('reports')) {
        body.classList.add('reports-section');
    } else if (path.includes('membership')) {
        body.classList.add('membership-section');
    }
}

// Handle online/offline events
window.addEventListener('online', function() {
    const userInfo = document.querySelector('[data-user-id]') || document.querySelector('.user-profile');
    if (userInfo) {
        Utils.showToast('Connection restored. Syncing data...', 'success');
        syncOfflineData();
    }
});

window.addEventListener('offline', function() {
    const userInfo = document.querySelector('[data-user-id]') || document.querySelector('.user-profile');
    if (userInfo) {
        Utils.showToast('You are offline. Showing cached data.', 'warning');
        loadOfflineData();
    }
});

// Enhanced loan calculation with new loan types
function calculateEnhancedLoanDetails() {
    const amount = parseFloat(document.getElementById('loanAmount')?.value) || 0;
    const category = document.getElementById('loanCategory')?.value || 'Short-term';
    const duration = parseInt(document.getElementById('durationMonths')?.value) || 3;

    let interestRate = 15; // Default for short-term
    if (category === 'Long-term') interestRate = 20;
    if (category === 'Emergency') interestRate = 10;

    const interest = amount * (interestRate / 100) * (duration / 12);
    const totalRepayment = amount + interest;
    const monthlyPayment = totalRepayment / duration;

    // Update display elements if they exist
    const principalEl = document.getElementById('principalAmount');
    const interestEl = document.getElementById('interestAmount');
    const totalEl = document.getElementById('totalRepayment');
    const monthlyEl = document.getElementById('monthlyPayment');
    const rateEl = document.getElementById('interestRate');

    if (principalEl) principalEl.textContent = 'KSh ' + amount.toLocaleString();
    if (interestEl) interestEl.textContent = 'KSh ' + interest.toLocaleString();
    if (totalEl) totalEl.textContent = 'KSh ' + totalRepayment.toLocaleString();
    if (monthlyEl) monthlyEl.textContent = 'KSh ' + monthlyPayment.toLocaleString();
    if (rateEl) rateEl.textContent = interestRate;
}

// Show/hide emergency type field
function toggleEmergencyFields() {
    const categorySelect = document.getElementById('loanCategory');
    const emergencyField = document.getElementById('emergency_type')?.closest('.col-12');

    if (categorySelect && emergencyField) {
        if (categorySelect.value === 'Emergency') {
            emergencyField.style.display = 'block';
            document.getElementById('emergency_type').required = true;
        } else {
            emergencyField.style.display = 'none';
            document.getElementById('emergency_type').required = false;
        }
    }
}

// Initialize relative time displays
function initializeRelativeTime() {
    const timeElements = document.querySelectorAll('.time-ago');

    timeElements.forEach(element => {
        const timeData = element.getAttribute('data-time');
        if (timeData) {
            try {
                const date = new Date(timeData);
                const relativeTime = getRelativeTime(date);

                // Create a more informative display
                const currentText = element.textContent;
                element.innerHTML = `
                    <span class="d-block">${currentText}</span>
                    <small class="text-muted" style="font-size: 0.75em;">${relativeTime}</small>
                `;

                // Update every minute for recent posts
                if (Date.now() - date.getTime() < 24 * 60 * 60 * 1000) { // Less than 24 hours old
                    setInterval(() => {
                        const newRelativeTime = getRelativeTime(date);
                        const smallElement = element.querySelector('small');
                        if (smallElement) {
                            smallElement.textContent = newRelativeTime;
                        }
                    }, 60000); // Update every minute
                }

            } catch (e) {
                console.warn('Invalid date format:', timeData);
            }
        }
    });
}

// Get relative time string (e.g., "2 hours ago", "just now")
function getRelativeTime(date) {
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);
    const diffWeeks = Math.floor(diffDays / 7);
    const diffMonths = Math.floor(diffDays / 30);
    const diffYears = Math.floor(diffDays / 365);

    if (diffMins < 1) {
        return 'Just now';
    } else if (diffMins < 60) {
        return `${diffMins} minute${diffMins !== 1 ? 's' : ''} ago`;
    } else if (diffHours < 24) {
        return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
    } else if (diffDays < 7) {
        return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
    } else if (diffWeeks < 4) {
        return `${diffWeeks} week${diffWeeks !== 1 ? 's' : ''} ago`;
    } else if (diffMonths < 12) {
        return `${diffMonths} month${diffMonths !== 1 ? 's' : ''} ago`;
    } else {
        return `${diffYears} year${diffYears !== 1 ? 's' : ''} ago`;
    }
}

// Format date to local timezone
function formatToLocalTime(dateString) {
    try {
        const date = new Date(dateString);
        return date.toLocaleString(undefined, {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            hour12: true,
            timeZoneName: 'short'
        });
    } catch (e) {
        return dateString; // fallback to original
    }
}

// Delete functionality with reason
function showDeleteModal(type, id, name) {
    const modal = document.getElementById('deleteModal');
    const form = modal.querySelector('form');
    const itemName = modal.querySelector('#deleteItemName');
    const itemType = modal.querySelector('#deleteItemType');

    itemName.textContent = name;
    itemType.textContent = type;

    form.action = `/${type}s/${id}/delete`;

    // Add CSRF token if not present
    if (!form.querySelector('input[name="csrf_token"]')) {
        const csrfInput = document.createElement('input');
        csrfInput.type = 'hidden';
        csrfInput.name = 'csrf_token';
        csrfInput.value = document.querySelector('meta[name="csrf-token"]')?.content || '';
        form.appendChild(csrfInput);
    }

    new bootstrap.Modal(modal).show();
}

// Loan approval modal functionality
function showLoanApprovalModal(loanId) {
    const modal = document.getElementById('loanApprovalModal');
    if (!modal) {
        console.error('Loan approval modal not found');
        return;
    }

    // Set the loan ID in the form
    const form = modal.querySelector('form');
    if (form) {
        form.action = `/loans/${loanId}/approve`;

        // Add CSRF token
        if (!form.querySelector('input[name="csrf_token"]')) {
            const csrfInput = document.createElement('input');
            csrfInput.type = 'hidden';
            csrfInput.name = 'csrf_token';
            csrfInput.value = document.querySelector('meta[name="csrf-token"]')?.content || '';
            form.appendChild(csrfInput);
        }
    }

    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
            }
