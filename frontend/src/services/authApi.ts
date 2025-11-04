/**
 * Authentication API Service
 *
 * Handles all authentication-related API calls to the user service.
 */

import axios, { AxiosError } from 'axios';

// API base URL - user service
const USER_SERVICE_URL = import.meta.env.VITE_USER_SERVICE_URL || 'http://localhost:8001/v1';

// Create axios instance with interceptors
export const apiClient = axios.create({
  baseURL: USER_SERVICE_URL,
  withCredentials: true, // For refresh token cookie
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add access token to requests
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Handle token refresh on 401
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest: any = error.config;

    // If 401 and not already retrying
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        // Try to refresh token
        const response = await axios.post(
          `${USER_SERVICE_URL}/auth/refresh`,
          {},
          { withCredentials: true }
        );

        const newAccessToken = response.data.access_token;

        // Update stored token
        localStorage.setItem('access_token', newAccessToken);

        // Retry original request with new token
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        // Refresh failed - redirect to login
        console.error('Token refresh failed, redirecting to login');
        localStorage.removeItem('access_token');
        window.location.href = '/login';
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

// Auth API methods
export const authApi = {
  /**
   * Register a new user
   */
  register: async (data: {
    email: string;
    password: string;
    name: string;
    phone?: string;
  }) => {
    const response = await apiClient.post('/auth/register', data);
    return response.data;
  },

  /**
   * Login with email and password
   */
  login: async (email: string, password: string) => {
    const response = await apiClient.post('/auth/login', {
      email,
      password,
      persist_session: true, // Keep user logged in
    });

    // Store access token if provided
    if (response.data.access_token) {
      localStorage.setItem('access_token', response.data.access_token);
    }

    return response.data;
  },

  /**
   * Verify MFA code
   */
  verifyMfa: async (sessionToken: string, code: string) => {
    const response = await apiClient.post('/auth/mfa/verify', {
      session_token: sessionToken,
      code,
    });

    // Store access token
    if (response.data.access_token) {
      localStorage.setItem('access_token', response.data.access_token);
    }

    return response.data;
  },

  /**
   * Logout
   */
  logout: async (allDevices = false) => {
    await apiClient.post('/auth/logout', { all_devices: allDevices });
    localStorage.removeItem('access_token');
  },

  /**
   * Refresh access token
   */
  refreshToken: async () => {
    const response = await apiClient.post('/auth/refresh');
    return response.data;
  },

  /**
   * Get current user info
   */
  getCurrentUser: async () => {
    const response = await apiClient.get('/users/me');
    return response.data;
  },

  /**
   * Request password reset
   */
  requestPasswordReset: async (email: string) => {
    const response = await apiClient.post('/auth/password/reset-request', { email });
    return response.data;
  },

  /**
   * Reset password with token
   */
  resetPassword: async (token: string, newPassword: string) => {
    const response = await apiClient.post('/auth/password/reset', {
      token,
      new_password: newPassword,
    });
    return response.data;
  },

  /**
   * Change password (authenticated)
   */
  changePassword: async (oldPassword: string, newPassword: string) => {
    const response = await apiClient.post('/users/password', {
      old_password: oldPassword,
      new_password: newPassword,
    });
    return response.data;
  },

  /**
   * Update user profile
   */
  updateProfile: async (data: { name?: string; phone?: string }) => {
    const response = await apiClient.put('/users/me', data);
    return response.data;
  },
};

// MFA API methods
export const mfaApi = {
  /**
   * Setup TOTP (get QR code)
   */
  setupTotp: async () => {
    const response = await apiClient.post('/mfa/totp/setup');
    return response.data;
  },

  /**
   * Enable TOTP (verify and activate)
   */
  enableTotp: async (code: string) => {
    const response = await apiClient.post('/mfa/totp/enable', { code });
    return response.data;
  },

  /**
   * Disable TOTP
   */
  disableTotp: async (password: string) => {
    const response = await apiClient.post('/mfa/totp/disable', { password });
    return response.data;
  },

  /**
   * Regenerate backup codes
   */
  regenerateBackupCodes: async () => {
    const response = await apiClient.post('/mfa/totp/backup-codes/regenerate');
    return response.data;
  },
};

// Trading accounts API methods
export const tradingAccountApi = {
  /**
   * List trading accounts
   */
  listAccounts: async () => {
    const response = await apiClient.get('/trading-accounts');
    return response.data;
  },

  /**
   * Link a new trading account
   */
  linkAccount: async (data: {
    broker: string;
    user_id_broker: string;
    api_key: string;
    api_secret: string;
  }) => {
    const response = await apiClient.post('/trading-accounts', data);
    return response.data;
  },

  /**
   * Verify trading account
   */
  verifyAccount: async (accountId: string) => {
    const response = await apiClient.post(`/trading-accounts/${accountId}/verify`);
    return response.data;
  },

  /**
   * Delete trading account
   */
  deleteAccount: async (accountId: string) => {
    await apiClient.delete(`/trading-accounts/${accountId}`);
  },
};

// Sessions API methods
export const sessionsApi = {
  /**
   * List active sessions
   */
  listSessions: async () => {
    const response = await apiClient.get('/users/sessions');
    return response.data;
  },

  /**
   * Revoke a session
   */
  revokeSession: async (sessionId: string) => {
    await apiClient.delete(`/users/sessions/${sessionId}`);
  },
};

export default apiClient;
