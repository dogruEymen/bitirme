import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import './App.css';
import Layout from './components/Layout';
import ChatPage from './pages/ChatPage';
import DashboardPage from './pages/DashboardPage';
import BulletinPage from './pages/BulletinPage';
import AuthPage from './pages/AuthPage';
import RequireAuth from './components/RequireAuth';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Navigate to="/session/new" replace />} />
          <Route
            path="/session/:sessionId"
            element={
              <RequireAuth>
                <ChatPage />
              </RequireAuth>
            }
          />
          <Route
            path="/dashboard"
            element={
              <RequireAuth>
                <DashboardPage />
              </RequireAuth>
            }
          />
          <Route
            path="/bulletin"
            element={
              <RequireAuth>
                <BulletinPage />
              </RequireAuth>
            }
          />
          <Route path="/auth" element={<AuthPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
