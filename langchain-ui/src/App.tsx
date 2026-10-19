import { NotFound } from './pages/NotFound';
import { DevUI } from './pages/DevUI';
import { adoptServerPreferences } from './lib/appearance';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Home } from './pages/Home';
import { RunDashboard } from './pages/RunDashboard';
import { RunList } from './pages/RunList';
import { Login } from './pages/Login';
import { Settings } from './pages/Settings';
import React, { useEffect, useState } from 'react';
import { api } from './api';
import { FeedbackProvider } from './components/Feedback';

class ErrorBoundary extends React.Component<{children: React.ReactNode}, {hasError: boolean, error: any}> {
  constructor(props: any) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error: any) {
    return { hasError: true, error };
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '2rem', textAlign: 'center' }}>
          <h2>Something went wrong.</h2>
          <pre style={{ textAlign: 'left', background: 'var(--bg-inset)', color: 'var(--fg)', padding: '1rem', overflow: 'auto' }}>
            {this.state.error?.toString()}
          </pre>
          <button onClick={() => window.location.reload()} style={{ marginTop: '1rem', padding: '0.5rem 1rem' }}>
            Reload Application
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const token = localStorage.getItem('token');
  const [isValidating, setIsValidating] = useState(true);
  const [isValid, setIsValid] = useState(false);

  useEffect(() => {
    if (!token) {
      setIsValidating(false);
      return;
    }

    let isMounted = true;
    const checkToken = async () => {
      try {
        const me = await api.get('/auth/me');
        adoptServerPreferences(me.data?.preferences);
        if (isMounted) setIsValid(true);
      } catch {
        // Clearing the token is enough: the render path below redirects to
        // /login whenever the session fails to validate, so an imperative
        // navigate here would only duplicate that and race with it.
        localStorage.removeItem('token');
        if (isMounted) setIsValid(false);
      } finally {
        if (isMounted) setIsValidating(false);
      }
    };

    checkToken();
    const interval = setInterval(checkToken, 60000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [token, location]);

  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  
  if (isValidating) {
    return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>Verifying session...</div>;
  }

  return isValid ? <>{children}</> : <Navigate to="/login" state={{ from: location }} replace />;
}

function App() {
  return (
    <FeedbackProvider>
    <BrowserRouter>
      <ErrorBoundary>
        <Routes>
          <Route path="/login" element={<Login />} />
          {/* The component kit's page, for the accessibility measure and the theme screenshots; never in a production build. */}
          {import.meta.env.DEV && <Route path="/dev/ui" element={<DevUI />} />}
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Layout />
              </ProtectedRoute>
            }
          >
            <Route index element={<Home />} />
            <Route path="runs" element={<RunList />} />
            <Route path="runs/:runId" element={<RunDashboard />} />
            <Route path="settings" element={<Settings />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </ErrorBoundary>
    </BrowserRouter>
    </FeedbackProvider>
  );
}

export default App;
