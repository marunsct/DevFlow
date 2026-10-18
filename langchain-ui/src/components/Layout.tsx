import React from 'react';
import { Outlet, Link, useNavigate, useLocation } from 'react-router-dom';
import { Home, Layers, List, Settings, LogOut } from 'lucide-react';
import { ThemeToggle } from './ThemeToggle';

export const Header: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = () => {
    localStorage.removeItem('token');
    navigate('/login');
  };

  const isActive = (path: string) => {
    if (path === '/') return location.pathname === '/';
    return location.pathname.startsWith(path);
  };

  const linkClass = (path: string) =>
    `flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-200 ${
      isActive(path)
        ? 'bg-overlay-strong text-text-primary'
        : 'text-text-secondary hover:text-text-primary hover:bg-overlay'
    }`;

  return (
    <header className="sticky top-0 z-50 glass-card-strong border-b border-border">
      <div className="w-full px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          <Link to="/" className="flex items-center gap-2.5 group">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-primary to-primary-hover flex items-center justify-center shadow-lg shadow-primary/20 group-hover:shadow-primary/40 transition-shadow">
              <Layers className="h-4.5 w-4.5 text-text-primary" />
            </div>
            <span className="font-bold text-lg text-text-primary tracking-tight">
              DevFlow<span className="text-primary">.ai</span>
            </span>
          </Link>
          <nav className="flex items-center gap-1">
            <Link to="/" className={linkClass('/')} aria-label="Home" aria-current={isActive('/') ? 'page' : undefined}>
              <Home className="h-4 w-4" />
              <span className="hidden sm:inline">Home</span>
            </Link>
            <Link to="/runs" className={linkClass('/runs')} aria-label="Runs" aria-current={isActive('/runs') ? 'page' : undefined}>
              <List className="h-4 w-4" />
              <span className="hidden sm:inline">Runs</span>
            </Link>
            <Link to="/settings" className={linkClass('/settings')} aria-label="Settings" aria-current={isActive('/settings') ? 'page' : undefined}>
              <Settings className="h-4 w-4" />
              <span className="hidden sm:inline">Settings</span>
            </Link>
            <ThemeToggle />
            <div className="w-px h-6 bg-border mx-2" />
            <button
              onClick={handleLogout}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-text-secondary hover:text-danger hover:bg-danger-bg transition-all duration-200"
              title="Sign out"
            >
              <LogOut className="h-4 w-4" />
              <span className="sr-only sm:not-sr-only">Sign out</span>
            </button>
          </nav>
        </div>
      </div>
    </header>
  );
};

export const Layout: React.FC = () => {
  return (
    <div className="min-h-screen flex flex-col bg-canvas">
      <a href="#main" className="skip-link">Skip to content</a>
      <Header />
      {/* The run dashboard is a three-column workspace, so the shell takes the
          whole window. At max-w-7xl the rails were squeezed into ~18rem each on
          a 1080p display; capped at 120-140rem, a wider screen still sat empty
          on both sides. */}
      <main id="main" tabIndex={-1} className="flex-1 w-full px-4 sm:px-6 lg:px-8 py-6 focus:outline-none">
        <Outlet />
      </main>
      <footer className="border-t border-border/50 py-6 text-center text-xs text-text-muted">
        <p>&copy; {new Date().getFullYear()} DevFlow.ai — AI-Powered Product Development</p>
      </footer>
    </div>
  );
};
