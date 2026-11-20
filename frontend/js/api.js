/**
 * FormWise AI - API Service
 * Handles communication between Frontend and Flask Backend
 */

// Resolve API base URL dynamically.
// 1. If explicit window.FORMWISE_API_URL is configured, use it.
// 2. When frontend is served on port 5500, 8000, 3000, or 5173 (typical static dev servers),
//    route backend requests to Flask on port 5000 of the same hostname.
// 3. When frontend is served directly through Flask (same origin/port or reverse proxy),
//    use window.location.origin.
const API_BASE_URL = window.FORMWISE_API_URL || (
  ["5500", "8000", "3000", "5173"].includes(window.location.port)
    ? `${window.location.protocol}//${window.location.hostname}:5000`
    : window.location.origin
);

/**
 * Send a GET request to the Flask health endpoint.
 * @returns {Promise<Object>} JSON response object if successful, or null on error.
 */
async function checkBackend() {
  try {
    const response = await fetch(`${API_BASE_URL}/health`, {
      method: 'GET',
      headers: {
        'Accept': 'application/json'
      }
    });

    if (!response.ok) {
      throw new Error(`HTTP error! Status: ${response.status}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.warn('Backend connection error:', error);
    return null;
  }
}

/**
 * Updates the backend connection status indicator in the UI.
 */
async function updateBackendStatus() {
  const statusEl = document.getElementById('backendStatus');
  const textEl = document.getElementById('backendStatusText');
  const statusElements = document.querySelectorAll('.backend-status');
  const textElements = document.querySelectorAll('.backend-status-text');

  // Initial checking state
  if (textEl) textEl.textContent = 'Checking Backend...';
  if (statusEl) statusEl.className = 'backend-status checking';
  textElements.forEach(el => el.textContent = 'Checking Backend...');
  statusElements.forEach(el => el.className = 'backend-status checking');

  const result = await checkBackend();

  if (result && result.status === 'success') {
    if (textEl) textEl.textContent = 'Backend Connected';
    if (statusEl) statusEl.className = 'backend-status connected';
    textElements.forEach(el => el.textContent = 'Backend Connected');
    statusElements.forEach(el => el.className = 'backend-status connected');
  } else {
    if (textEl) textEl.textContent = 'Backend Disconnected';
    if (statusEl) statusEl.className = 'backend-status disconnected';
    textElements.forEach(el => el.textContent = 'Backend Disconnected');
    statusElements.forEach(el => el.className = 'backend-status disconnected');
  }
}

// Automatically check status on page load
document.addEventListener('DOMContentLoaded', () => {
  updateBackendStatus();
});
