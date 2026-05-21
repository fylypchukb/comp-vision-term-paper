/**
 * Modal — generic overlay modal wrapper.
 * Closes on backdrop click and on Escape key.
 */

import { useEffect } from 'react';
import './Modal.css';

interface Props {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  /** Extra CSS class on the dialog panel. */
  className?: string;
}

export default function Modal({ title, onClose, children, className = '' }: Props) {
  // Close on Escape key
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className={`modal-panel ${className}`}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
      >
        <div className="modal-header">
          <h2 id="modal-title" className="modal-title">{title}</h2>
          <button className="modal-close" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}
