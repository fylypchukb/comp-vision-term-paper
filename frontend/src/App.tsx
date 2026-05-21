/**
 * App.tsx — root component.
 *
 * Sets up React Router routes and wraps the entire tree in AppProvider so
 * all child components have access to global state and WebSocket events.
 */

import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AppProvider } from './context/AppContext';
import Navbar from './components/Navbar/Navbar';
import Dashboard from './pages/Dashboard/Dashboard';
import LockDetail from './pages/LockDetail/LockDetail';
import Users from './pages/Users/Users';
import EventLog from './pages/EventLog/EventLog';
import './App.css';

export default function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <Navbar />
        <div className="app-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/locks/:id" element={<LockDetail />} />
            <Route path="/users" element={<Users />} />
            <Route path="/log" element={<EventLog />} />
          </Routes>
        </div>
      </BrowserRouter>
    </AppProvider>
  );
}
