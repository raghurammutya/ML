/**
 * Authentication Context for Frontend
 *
 * Manages user authentication state and provides auth methods.
 */

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { authApi } from '../services/authApi';

// User type
export interface User {
  user_id: number;
  email: string;
  name: string;
  phone?: string;
  roles: string[];
  mfa_enabled: boolean;
  created_at: string;
}

// Auth context type
interface AuthContextType {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<LoginResponse>;
  logout: () => Promise<void>;
  verifyMfa: (sessionToken: string, code: string) => Promise<void>;
  refreshToken: () => Promise<void>;
  checkAuth: () => Promise<void>;
}

// Login response type
export interface LoginResponse {
  status: 'success' | 'mfa_required';
  access_token?: string;
  token_type?: string;
  expires_in?: number;
  user?: User;
  session_token?: string; // For MFA verification
}

// Create context
const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Provider component
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Check if user is authenticated on mount
  useEffect(() => {
    checkAuth();

    // Set up token refresh timer (refresh every 14 minutes, token expires in 15)
    const interval = setInterval(() => {
      refreshToken();
    }, 14 * 60 * 1000);

    return () => clearInterval(interval);
  }, []);

  // Check authentication status
  const checkAuth = async () => {
    setIsLoading(true);

    try {
      const token = localStorage.getItem('access_token');
      if (!token) {
        setUser(null);
        setAccessToken(null);
        setIsLoading(false);
        return;
      }

      // Verify token is still valid by fetching user info
      const response = await authApi.getCurrentUser();
      setUser(response);
      setAccessToken(token);
    } catch (error) {
      console.error('Auth check failed:', error);
      // Token expired or invalid - clear state
      localStorage.removeItem('access_token');
      setUser(null);
      setAccessToken(null);
    } finally {
      setIsLoading(false);
    }
  };

  // Login function
  const login = async (email: string, password: string): Promise<LoginResponse> => {
    try {
      const response = await authApi.login(email, password);

      if (response.status === 'mfa_required') {
        // MFA required - return session token for verification
        return response;
      }

      // Login successful - store token and user
      if (response.access_token) {
        localStorage.setItem('access_token', response.access_token);
        setAccessToken(response.access_token);
      }

      if (response.user) {
        setUser(response.user);
      }

      return response;
    } catch (error: any) {
      console.error('Login failed:', error);
      throw new Error(error.response?.data?.detail || 'Login failed');
    }
  };

  // MFA verification function
  const verifyMfa = async (sessionToken: string, code: string) => {
    try {
      const response = await authApi.verifyMfa(sessionToken, code);

      // MFA verified - store token and user
      localStorage.setItem('access_token', response.access_token);
      setAccessToken(response.access_token);
      setUser(response.user);
    } catch (error: any) {
      console.error('MFA verification failed:', error);
      throw new Error(error.response?.data?.detail || 'MFA verification failed');
    }
  };

  // Logout function
  const logout = async () => {
    try {
      await authApi.logout();
    } catch (error) {
      console.error('Logout API call failed:', error);
      // Continue with local logout even if API call fails
    } finally {
      // Clear local state
      localStorage.removeItem('access_token');
      setAccessToken(null);
      setUser(null);
    }
  };

  // Refresh token function
  const refreshToken = async () => {
    try {
      const response = await authApi.refreshToken();

      // Update access token
      localStorage.setItem('access_token', response.access_token);
      setAccessToken(response.access_token);

      console.log('Token refreshed successfully');
    } catch (error) {
      console.error('Token refresh failed:', error);
      // Refresh failed - logout user
      await logout();
    }
  };

  const value: AuthContextType = {
    user,
    accessToken,
    isAuthenticated: !!user && !!accessToken,
    isLoading,
    login,
    logout,
    verifyMfa,
    refreshToken,
    checkAuth,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// Custom hook to use auth context
export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
