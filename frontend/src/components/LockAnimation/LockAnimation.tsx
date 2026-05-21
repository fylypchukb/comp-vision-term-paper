/**
 * LockAnimation — animated SVG padlock that transitions between
 * locked (shackle closed, red) and unlocked (shackle open, green) states.
 */

import './LockAnimation.css';

interface Props {
  state: 'locked' | 'unlocked' | 'unknown';
  size?: number;
}

export default function LockAnimation({ state, size = 80 }: Props) {
  const isUnlocked = state === 'unlocked';
  const isUnknown = state === 'unknown';

  return (
    <div
      className={`lock-anim ${state}`}
      style={{ width: size, height: size }}
      aria-label={`Lock is ${state}`}
    >
      <svg
        viewBox="0 0 64 72"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="lock-svg"
      >
        {/* Shackle (the U-shaped arch) */}
        <path
          className={`shackle ${isUnlocked ? 'open' : 'closed'}`}
          d={
            isUnlocked
              ? /* open — right side raised */
                'M16 34 C16 18 28 10 32 10 C36 10 48 18 48 34'
              : /* closed */
                'M16 34 C16 10 48 10 48 34'
          }
          strokeWidth="6"
          strokeLinecap="round"
          fill="none"
        />

        {/* Lock body */}
        <rect
          className="lock-body"
          x="8"
          y="33"
          width="48"
          height="34"
          rx="6"
        />

        {/* Keyhole circle */}
        <circle cx="32" cy="48" r="5" className="keyhole" />

        {/* Keyhole stem */}
        <rect x="29.5" y="50" width="5" height="8" rx="2" className="keyhole" />

        {isUnknown && (
          <text x="32" y="52" textAnchor="middle" fontSize="12" fill="currentColor">
            ?
          </text>
        )}
      </svg>
    </div>
  );
}
