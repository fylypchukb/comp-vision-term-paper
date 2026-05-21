/**
 * GestureGuide — reference card showing all 12 supported gestures.
 *
 * Rendered inside the recording panel so the user knows exactly which
 * gestures they can use when building a PIN sequence.
 */

import './GestureGuide.css';

interface Gesture {
  code: string;
  emoji: string;
  label: string;
  description: string;
}

// Removed: THUMBS_UP, THUMBS_DOWN (orientation-dependent, unreliable),
//          CALL_ME (thumb+pinky — hand tilt makes pinky Y-check flip to FIST).
// Replaced by: RING_PINKY and FINGER_GUN.
const GESTURES: Gesture[] = [
  { code: 'OPEN_PALM',  emoji: '✋', label: 'Open Palm',   description: 'All 5 fingers extended' },
  { code: 'FIST',       emoji: '✊', label: 'Fist',        description: '4 main fingers curled' },
  { code: 'INDEX_UP',   emoji: '☝️', label: 'Index Up',    description: 'Only index finger up' },
  { code: 'PEACE',      emoji: '✌️', label: 'Peace',       description: 'Index + middle up' },
  { code: 'THREE',      emoji: '🤟', label: 'Three',       description: 'Index + middle + ring' },
  { code: 'FOUR',       emoji: '🖖', label: 'Four',        description: 'All except thumb' },
  { code: 'PINKY_UP',   emoji: '🤙', label: 'Pinky Up',    description: 'Only pinky extended' },
  { code: 'OK',         emoji: '👌', label: 'OK',          description: 'Thumb + index circle' },
  { code: 'ROCK',       emoji: '🤘', label: 'Rock',        description: 'Index + pinky up' },
  { code: 'VULCAN',     emoji: '🖖', label: 'Vulcan',       description: 'Four fingers, middle/ring split' },
  { code: 'FINGER_GUN', emoji: '🫵', label: 'Finger Gun',  description: 'Thumb + index extended' },
];

interface Props {
  /** Highlight these gesture codes as already used in the current sequence. */
  usedGestures?: string[];
}

export default function GestureGuide({ usedGestures = [] }: Props) {
  return (
    <div className="gesture-guide">
      <p className="guide-title">Available gestures</p>
      <div className="guide-grid">
        {GESTURES.map((g) => {
          const usedCount = usedGestures.filter((u) => u === g.code).length;
          return (
            <div
              key={g.code}
              className={`guide-item ${usedCount > 0 ? 'used' : ''}`}
              title={g.description}
            >
              <span className="guide-emoji" role="img" aria-label={g.label}>
                {g.emoji}
              </span>
              <span className="guide-label">{g.label}</span>
              {usedCount > 0 && (
                <span className="guide-used-badge">×{usedCount}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
