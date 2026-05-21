/**
 * Navbar — top navigation bar with route links and WebSocket status indicator.
 */

import { NavLink } from 'react-router-dom';
import { useApp } from '../../context/AppContext';
import './Navbar.css';

export default function Navbar() {
  const { state } = useApp();

  return (
    <nav className="navbar">
      <div className="navbar-brand">
        <span className="navbar-logo">🔐</span>
        <span className="navbar-title">Gesture Smart Lock</span>
      </div>

      <div className="navbar-links">
        <NavLink
          to="/"
          end
          className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
        >
          Dashboard
        </NavLink>
        <NavLink
          to="/users"
          className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
        >
          Users
        </NavLink>
        <NavLink
          to="/log"
          className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
        >
          Event Log
        </NavLink>
      </div>

      <div className="navbar-status">
        <span
          className={`ws-dot ${state.wsConnected ? 'connected' : 'disconnected'}`}
          title={state.wsConnected ? 'WebSocket connected' : 'WebSocket disconnected'}
        />
        <span className="ws-label">
          {state.wsConnected ? 'Live' : 'Offline'}
        </span>
      </div>
    </nav>
  );
}
