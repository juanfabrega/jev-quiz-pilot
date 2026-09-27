// The visible HTML of a question block, stripped to structure: no scripts, styles, images, or hidden
// elements, and only the attributes that say what an element is. Jev reads it to tell the question
// from explanations and site text.
(sel) => {
  const KEEP = ['id', 'class', 'type', 'name', 'role', 'for', 'href', 'aria-label', 'placeholder'];
  const walk = e => {
    if (e.nodeType === 3) { const t = e.textContent.replace(/\s+/g, ' '); return t.trim() ? t : ''; }
    if (e.nodeType !== 1) return '';
    const tag = e.tagName.toLowerCase();
    if (['script', 'style', 'svg', 'noscript', 'iframe', 'link', 'meta', 'img'].includes(tag)) return '';
    if (e.checkVisibility && !e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})) return '';
    const attrs = KEEP.filter(a => e.hasAttribute(a)).map(a => ` ${a}="${String(e.getAttribute(a)).slice(0, 40)}"`).join('');
    const inner = [...e.childNodes].map(walk).join('');
    if (!inner && !['input', 'select', 'textarea', 'button'].includes(tag)) return '';
    return `<${tag}${attrs}>${inner}</${tag}>`;
  };
  return walk(document.querySelector(sel)).slice(0, 20000);
}
