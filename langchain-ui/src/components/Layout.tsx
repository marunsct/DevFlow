import React from 'react';
import { Outlet, Link, useNavigate, useLocation } from 'react-router-dom';
import { Home, Layers, List, Settings, LogOut } from 'lucide-react';

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
        ? 'bg-white/10 text-white'
        : 'text-slate-400 hover:text-white hover:bg-white/5'
    }`;

  return (
    <header className="sticky top-0 z-50 glass-card-strong border-b border-border">
      <div className="mx-auto w-full max-w-[120rem] 2xl:max-w-[140rem] px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          <Link to="/" className="flex items-center gap-2.5 group">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-primary to-violet-500 flex items-center justify-center shadow-lg shadow-primary/20 group-hover:shadow-primary/40 transition-shadow">
              <Layers className="h-4.5 w-4.5 text-white" />
            </div>
            <span className="font-bold text-lg text-white tracking-tight">
              DevFlow<span className="text-primary">.ai</span>
            </span>
          </Link>
          <nav className="flex items-center gap-1">
            <Link to="/" className={linkClass('/')}>
              <Home className="h-4 w-4" />
              <span className="hidden sm:inline">Home</span>
            </Link>
            <Link to="/runs" className={linkClass('/runs')}>
              <List className="h-4 w-4" />
              <span className="hidden sm:inline">Runs</span>
            </Link>
            <Link to="/settings" className={linkClass('/settings')}>
              <Settings className="h-4 w-4" />
              <span className="hidden sm:inline">Settings</span>
            </Link>
            <div className="w-px h-6 bg-border mx-2" />
            <button
              onClick={handleLogout}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-slate-400 hover:text-red-400 hover:bg-red-500/10 transition-all duration-200"
              title="Sign out"
            >
              <LogOut className="h-4 w-4" />
              <span className="hidden sm:inline">Logout</span>
            </button>
          </nav>
        </div>
      </div>
    </header>
  );
};

export const Layout: React.FC = () => {
  return (
    <div className="min-h-screen flex flex-col bg-[#020617]">
      <Header />
      {/* The run dashboard is a three-column workspace, so the shell has to be
          wide enough to hold one. At max-w-7xl the rails were squeezed into
          ~18rem each on a 1080p display and a third of the screen sat empty. */}
      <main className="flex-1 w-full max-w-[120rem] 2xl:max-w-[140rem] mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <Outlet />
      </main>
      <footer className="border-t border-border/50 py-6 text-center text-xs text-text-muted">
        <p>&copy; {new Date().getFullYear()} DevFlow.ai — AI-Powered Product Development</p>
      </footer>
    </div>
  );
};
