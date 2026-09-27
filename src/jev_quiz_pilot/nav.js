// Finds what a person could click to move on: real buttons, and elements styled as clickable
// (cursor: pointer), such as a <div> reading "Next". Leaves out plain links, which lead to other
// pages, e.g. JetPunk's next quiz. Marks each with data-jev-nav and returns their labels, real buttons first.
() => {
  document.querySelectorAll('[data-jev-nav]').forEach(e => e.removeAttribute('data-jev-nav'));
  const vis = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const pointer = e => e && getComputedStyle(e).cursor === 'pointer';
  const labels = [];
  const real = [...document.querySelectorAll('button, input[type=submit], input[type=button], [role=button]')];
  const styled = [...document.querySelectorAll('a, div, span, li')].filter(e => {
    if (e.matches('[role=button]') || !pointer(e) || pointer(e.parentElement)) return false;
    return !(e.tagName === 'A' && e.getAttribute('href') && !/#|^javascript:/.test(e.getAttribute('href')));
  });
  [...real, ...styled].forEach(e => {  // real buttons first
    if (!vis(e)) return;
    const label = (e.innerText || e.value || e.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ');
    if (!label || label.length > 40) return;
    e.setAttribute('data-jev-nav', labels.length);
    labels.push(label);
  });
  return labels;
}
