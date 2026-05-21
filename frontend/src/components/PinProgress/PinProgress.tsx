/**
 * PinProgress — visual indicator for PIN entry progress.
 *
 * Renders one dot per gesture in the sequence. Filled dots represent
 * gestures already entered; empty dots represent remaining slots.
 */

import './PinProgress.css';

const GESTURE_EMOJI: Record<string, string> = {
  OPEN_PALM: '✋', FIST: '✊', INDEX_UP: '☝️', PEACE: '✌️',
  THREE: '🤟', FOUR: '🖖', PINKY_UP: '🤙', OK: '👌',
  ROCK: '🤘', VULCAN: '🖖', FINGER_GUN: '🫵',
};

interface Props {
  /** Gestures entered so far in this attempt. */
  sequence: string[];
  /** Total PIN length (unknown → show entered sequence only). */
  total?: number;
  /** Colour the progress bar based on entry status. */
  status?: 'partial' | 'match' | 'fail' | 'recording';
}

export default function PinProgress({ sequence, total, status = 'partial' }: Props) {
  const len = total ?? sequence.length;

  return (
    <div className={`pin-progress ${status}`}>
      <div className="pin-dots">
        {Array.from({ length: len }).map((_, i) => {
          const gesture = sequence[i];
          return (
            <div
              key={i}
              className={`pin-dot ${gesture ? 'filled' : 'empty'}`}
              title={gesture ?? `Slot ${i + 1}`}
            >
              {gesture ? (
                <span className="dot-emoji">{GESTURE_EMOJI[gesture] ?? '🤚'}</span>
              ) : (
                <span className="dot-index">{i + 1}</span>
              )}
            </div>
          );
        })}
      </div>

      {sequence.length > 0 && (
        <div className="pin-counter">
          {sequence.length} / {len} gestures
        </div>
      )}
    </div>
  );
}
