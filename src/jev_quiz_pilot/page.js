// Helpers that run in the page. Each is an arrow function passed to page.evaluate.

// clickTarget: what to click so the option gets picked the way a person would pick it.
// Returns the input's own selector when nothing covers it. Otherwise marks the option's
// tile (the largest ancestor holding only this input, e.g. an <li>) and returns its selector.
(sel) => {
  document.querySelectorAll('[data-jev-click]').forEach(e => e.removeAttribute('data-jev-click'));
  const el = document.querySelector(sel);
  el.scrollIntoView({block: 'center'});
  const b = el.getBoundingClientRect();
  const hit = document.elementFromPoint(b.x + b.width / 2, b.y + b.height / 2);
  if (b.width && hit === el) return sel;
  // Covered by part of its own label, e.g. a styled overlay: clicking the label ticks the input.
  const label = b.width && hit && [...(el.labels || [])].find(l => l.contains(hit));
  if (label) { label.setAttribute('data-jev-click', ''); return '[data-jev-click]'; }
  let tile = el;
  while (tile.parentElement && tile.parentElement.querySelectorAll('input').length === 1) tile = tile.parentElement;
  tile.setAttribute('data-jev-click', '');
  return '[data-jev-click]';
}
