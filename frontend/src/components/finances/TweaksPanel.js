import React, { useEffect, useState } from 'react';

const STORAGE_KEY = 'eh.tweaks';

function loadTweaks() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    return JSON.parse(raw);
  } catch {
    return {};
  }
}

export default function TweaksPanel({ blurSensitive, onBlurChange }) {
  const [open, setOpen] = useState(false);
  const initial = loadTweaks();
  const [darkMode, setDarkMode] = useState(() => {
    if (initial.darkMode != null) return initial.darkMode;
    return localStorage.getItem('theme') === 'dark';
  });
  const [showProjections, setShowProjections] = useState(initial.showProjections ?? false);
  const [accent, setAccent] = useState(initial.accent || '#059669');

  // Persist tweaks (other than blur, which is owned by the dashboard).
  useEffect(() => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ darkMode, showProjections, accent })
    );
  }, [darkMode, showProjections, accent]);

  // Sync dark mode with the existing app theme attribute.
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', darkMode ? 'dark' : 'light');
    localStorage.setItem('theme', darkMode ? 'dark' : 'light');
  }, [darkMode]);

  // Apply accent to the CSS variable live.
  useEffect(() => {
    document.documentElement.style.setProperty('--accent', accent);
  }, [accent]);

  return (
    <>
      <button type="button" className="eh-tweaks-fab" onClick={() => setOpen((o) => !o)}
              aria-label="Open tweaks panel">
        ⚙ Tweaks
      </button>

      {open && (
        <div className="eh-tweaks-panel" role="dialog" aria-label="Display tweaks">
          <div className="eh-tweaks-title">Tweaks</div>

          <Toggle label="Dark mode" checked={darkMode} onChange={setDarkMode} />
          <Toggle label="Blur sensitive numbers" checked={blurSensitive} onChange={onBlurChange} />
          <Toggle label="Show spending projections" checked={showProjections} onChange={setShowProjections} />

          <div className="eh-tweak-row">
            <span>Primary color</span>
            <input
              type="color"
              value={accent}
              onChange={(e) => setAccent(e.target.value)}
              aria-label="Primary accent color"
            />
          </div>
        </div>
      )}
    </>
  );
}

function Toggle({ label, checked, onChange }) {
  return (
    <label className="eh-tweak-row">
      <span>{label}</span>
      <span className="eh-switch">
        <input type="checkbox" checked={!!checked} onChange={(e) => onChange(e.target.checked)} />
        <span className="eh-switch-slider" />
      </span>
    </label>
  );
}
