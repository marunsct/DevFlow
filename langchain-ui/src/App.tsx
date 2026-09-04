import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Home } from './pages/Home';
import { RunDashboard } from './pages/RunDashboard';
import { RunList } from './pages/RunList';
import { Login } from './pages/Login';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="runs" element={<RunList />} />
          <Route path="runs/:runId" element={<RunDashboard />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
