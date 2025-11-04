/**
 * Login Page
 *
 * Handles user login with email/password and MFA support.
 */

import { useState, FormEvent } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { useAuth, LoginResponse } from '../contexts/AuthContext';

export function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [mfaRequired, setMfaRequired] = useState(false);
  const [mfaCode, setMfaCode] = useState('');
  const [sessionToken, setSessionToken] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const { login, verifyMfa } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // Get redirect path from location state or default to home
  const from = (location.state as any)?.from?.pathname || '/';

  // Handle login form submission
  const handleLogin = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      const response: LoginResponse = await login(email, password);

      if (response.status === 'mfa_required') {
        // MFA required - show MFA form
        setMfaRequired(true);
        setSessionToken(response.session_token || '');
      } else {
        // Login successful - redirect
        navigate(from, { replace: true });
      }
    } catch (err: any) {
      setError(err.message || 'Login failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  // Handle MFA verification
  const handleMfaVerify = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      await verifyMfa(sessionToken, mfaCode);
      // MFA verified - redirect
      navigate(from, { replace: true });
    } catch (err: any) {
      setError(err.message || 'Invalid MFA code. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  // MFA verification form
  if (mfaRequired) {
    return (
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '100vh',
        background: '#f5f5f5'
      }}>
        <div style={{
          background: 'white',
          padding: '40px',
          borderRadius: '8px',
          boxShadow: '0 2px 10px rgba(0,0,0,0.1)',
          width: '100%',
          maxWidth: '400px'
        }}>
          <h1 style={{ marginBottom: '10px' }}>Two-Factor Authentication</h1>
          <p style={{ marginBottom: '30px', color: '#666' }}>
            Enter the 6-digit code from your authenticator app.
          </p>

          <form onSubmit={handleMfaVerify}>
            {error && (
              <div style={{
                padding: '10px',
                marginBottom: '20px',
                background: '#fee',
                color: '#c33',
                borderRadius: '4px',
                fontSize: '14px'
              }}>
                {error}
              </div>
            )}

            <div style={{ marginBottom: '20px' }}>
              <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500' }}>
                Verification Code
              </label>
              <input
                type="text"
                placeholder="000000"
                value={mfaCode}
                onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                maxLength={6}
                required
                autoFocus
                style={{
                  width: '100%',
                  padding: '12px',
                  fontSize: '18px',
                  border: '1px solid #ddd',
                  borderRadius: '4px',
                  letterSpacing: '0.5em',
                  textAlign: 'center'
                }}
              />
            </div>

            <button
              type="submit"
              disabled={isLoading || mfaCode.length !== 6}
              style={{
                width: '100%',
                padding: '12px',
                background: '#007bff',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                fontSize: '16px',
                fontWeight: '500',
                cursor: isLoading ? 'not-allowed' : 'pointer',
                opacity: isLoading || mfaCode.length !== 6 ? 0.6 : 1
              }}
            >
              {isLoading ? 'Verifying...' : 'Verify'}
            </button>

            <div style={{ marginTop: '20px', textAlign: 'center' }}>
              <button
                type="button"
                onClick={() => {
                  setMfaRequired(false);
                  setMfaCode('');
                  setSessionToken('');
                  setError('');
                }}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#007bff',
                  cursor: 'pointer',
                  textDecoration: 'underline',
                  fontSize: '14px'
                }}
              >
                Back to login
              </button>
            </div>
          </form>
        </div>
      </div>
    );
  }

  // Login form
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      minHeight: '100vh',
      background: '#f5f5f5'
    }}>
      <div style={{
        background: 'white',
        padding: '40px',
        borderRadius: '8px',
        boxShadow: '0 2px 10px rgba(0,0,0,0.1)',
        width: '100%',
        maxWidth: '400px'
      }}>
        <h1 style={{ marginBottom: '10px' }}>Login to Quantagro</h1>
        <p style={{ marginBottom: '30px', color: '#666' }}>
          Sign in to access your trading platform.
        </p>

        <form onSubmit={handleLogin}>
          {error && (
            <div style={{
              padding: '10px',
              marginBottom: '20px',
              background: '#fee',
              color: '#c33',
              borderRadius: '4px',
              fontSize: '14px'
            }}>
              {error}
            </div>
          )}

          <div style={{ marginBottom: '20px' }}>
            <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500' }}>
              Email
            </label>
            <input
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
              style={{
                width: '100%',
                padding: '12px',
                fontSize: '14px',
                border: '1px solid #ddd',
                borderRadius: '4px'
              }}
            />
          </div>

          <div style={{ marginBottom: '20px' }}>
            <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500' }}>
              Password
            </label>
            <input
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              style={{
                width: '100%',
                padding: '12px',
                fontSize: '14px',
                border: '1px solid #ddd',
                borderRadius: '4px'
              }}
            />
          </div>

          <button
            type="submit"
            disabled={isLoading}
            style={{
              width: '100%',
              padding: '12px',
              background: '#007bff',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              fontSize: '16px',
              fontWeight: '500',
              cursor: isLoading ? 'not-allowed' : 'pointer',
              opacity: isLoading ? 0.6 : 1
            }}
          >
            {isLoading ? 'Signing in...' : 'Sign In'}
          </button>

          <div style={{
            marginTop: '20px',
            textAlign: 'center',
            fontSize: '14px'
          }}>
            <Link to="/forgot-password" style={{ color: '#007bff', textDecoration: 'none' }}>
              Forgot password?
            </Link>
          </div>

          <div style={{
            marginTop: '10px',
            textAlign: 'center',
            fontSize: '14px'
          }}>
            <span style={{ color: '#666' }}>Don't have an account? </span>
            <Link to="/register" style={{ color: '#007bff', textDecoration: 'none' }}>
              Register
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
