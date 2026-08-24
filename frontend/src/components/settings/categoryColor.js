// Swatch palette from the design handoff.
const SWATCHES = [
  '#e87455', '#e08e3a', '#9579c8', '#5a9e8f',
  '#c8697f', '#6d8ec4', '#d0a24a', '#7fa05a',
];

/**
 * Stable colour for a category name.
 *
 * Derived rather than stored: categories are a union of transaction
 * labels, budgets, and built-in defaults with no table of their own, so
 * there is nowhere to persist a chosen colour. Hashing the name keeps the
 * swatch identical across sessions and machines without a schema. Swap
 * this for a lookup if category editing ever lands.
 */
export default function categoryColor(name) {
  const key = (name || '').trim().toLowerCase();
  if (!key) return SWATCHES[0];
  let hash = 0;
  for (let i = 0; i < key.length; i += 1) {
    hash = (hash * 31 + key.charCodeAt(i)) | 0;
  }
  return SWATCHES[Math.abs(hash) % SWATCHES.length];
}
