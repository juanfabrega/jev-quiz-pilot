// Runs in the page: finds visible fields, tags them with data-jev ids, returns a summary.
() => {
  const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const txt = el => (el ? el.innerText || el.textContent || '' : '').trim().replace(/\s+/g, ' ');
  const labelFor = el => {
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) return txt(l); }
    const wrap = el.closest('label'); if (wrap) return txt(wrap);
    return el.getAttribute('aria-label') || el.placeholder || el.name || '';
  };
  const questionFor = el => {
    const fs = el.closest('fieldset'); if (fs && fs.querySelector('legend')) return txt(fs.querySelector('legend'));
    const grp = el.closest('[role=radiogroup],[role=group],[role=listitem]');
    if (grp) {
      const lb = grp.getAttribute('aria-labelledby');
      if (lb) { const e = document.getElementById(lb.split(' ')[0]); if (e) return txt(e); }
      if (grp.getAttribute('aria-label')) return grp.getAttribute('aria-label');
      const h = grp.querySelector('[role=heading],h1,h2,h3,h4,legend'); if (h) return txt(h);
    }
    return labelFor(el);
  };
  const fields = [];
  document.querySelectorAll('input, select, textarea').forEach((el, i) => {
    if (!vis(el) || el.disabled) return;
    const t = (el.type || '').toLowerCase();
    if (['hidden','submit','button','reset','image','file','password'].includes(t)) return;
    el.setAttribute('data-jev', i);
    const sel = `[data-jev="${i}"]`;
    if (t === 'radio' || t === 'checkbox') {
      const key = t + ':' + (el.name || i);
      let f = fields.find(x => x.key === key);
      if (!f) { f = {key, kind: t, question: questionFor(el), options: []}; fields.push(f); }
      f.options.push({label: labelFor(el), sel});
    } else if (el.tagName === 'SELECT') {
      fields.push({key: 'select:' + i, kind: 'select', question: questionFor(el), sel,
        options: [...el.options].filter(o => o.value).map(o => ({label: o.text.trim(), value: o.value}))});
    } else {
      fields.push({key: 'text:' + i, kind: 'text', question: labelFor(el), sel, filled: !!el.value,
        multiline: el.tagName === 'TEXTAREA'});
    }
  });
  return fields;
}
