/**
 * GestureIndicator — shows the currently recognised gesture with its emoji
 * and a colour-coded border reflecting the entry status (partial / match / fail).
 */

import './GestureIndicator.css';

/** Emoji map for the 10 active gestures. */
const GESTURE_EMOJI: Record<string, string> = {
  OPEN_PALM:  '✋',
  FIST:       '✊',
  INDEX_UP:   '☝️',
  PEACE:      '✌️',
  THREE:      '🤟',
  FOUR:       '🖖',
  PINKY_UP:   '🤙',
  OK:         '👌',
  ROCK:       '🤘',
  VULCAN:     '🖖',
  FINGER_GUN: '🫵',
};

const GESTURE_LABEL: Record<string, string> = {
  OPEN_PALM:  'Open Palm',
  FIST:       'Fist',
  INDEX_UP:   'Index Up',
  PEACE:      'Peace',
  THREE:      'Three',
  FOUR:       'Four',
  PINKY_UP:   'Pinky Up',
  OK:         'OK',
  ROCK:       'Rock',
  VULCAN:     'Vulcan',
  FINGER_GUN: 'Finger Gun',
};

interface Props {
  gesture: string | null;
  status?: 'partial' | 'match' | 'fail' | 'recording';
  /** Label below the gesture (e.g. "Recording gesture 2/4") */
  label?: string;
}

export default function GestureIndicator({ gesture, status = 'partial', label }: Props) {
  if (!gesture) {
    return (
      <div className="gesture-indicator empty">
        <span className="gesture-emoji">👋</span>
        <span className="gesture-name">Waiting…</span>
      </div>
    );
  }

  return (
    <div className={`gesture-indicator ${status}`}>
      <span className="gesture-emoji" role="img" aria-label={gesture}>
        {GESTURE_EMOJI[gesture] ?? '🤚'}
      </span>
      <span className="gesture-name">{GESTURE_LABEL[gesture] ?? gesture}</span>
      {label && <span className="gesture-sub">{label}</span>}
    </div>
  );
}
