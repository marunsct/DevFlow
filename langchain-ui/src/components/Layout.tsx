import React from 'react';
import { Outlet, Link } from 'react-router-dom';
import { Home, Layers, Settings } from 'lucide-react';

export const Header: React.FC = () => {
  return (
    <header className="bg-primary text-primary-foreground shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          <div className="flex items-center gap-2">
            <Layers className="h-6 w-6 text-success" />
            <span className="font-bold text-xl tracking-tight">Product Workflow</span>
          </div>
          <nav className="flex items-center gap-6">
            <Link to="/" className="flex items-center gap-1.5 text-sm font-medium hover:text-success transition-colors">
              <Home className="h-4 w-4" />
              Home
            </Link>
            <Link to="/runs" className="flex items-center gap-1.5 text-sm font-medium hover:text-success transition-colors">
              <Settings className="h-4 w-4" />
              Settings
            </Link>
          </nav>
        </div>
      </div>
    </header>
  );
};

export const Layout: React.FC = () => {
  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <Header />
      <main className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Outlet />
      </main>
      <footer className="bg-white border-t py-6 text-center text-sm text-muted">
        <p>&copy; {new Date().getFullYear()} Product Development Workflow</p>
      </footer>
    </div>
  );
};
