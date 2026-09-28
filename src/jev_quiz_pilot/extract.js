// Runs in the page: finds visible fields, tags them with data-jev ids, returns a summary.
() => {
  const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const txt = el => (el ? el.innerText || el.textContent || '' : '').trim().replace(/\s+/g, ' ');
  const labelFor = el => {
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) return txt(l); }
    const wrap = el.closest('label'); if (wrap) return txt(wrap);
    const lb = el.getAttribute('aria-labelledby') && document.getElementById(el.getAttribute('aria-labelledby').split(' ')[0]);
    if (lb && txt(lb)) return txt(lb);  // e.g. Google Forms text boxes
    return el.getAttribute('aria-label') || el.placeholder || el.name || '';
  };
  // A question's description, such as "you need to select 2 options": what the nearest aria-describedby names.
  const hintFor = el => {
    const d = el.closest('[aria-describedby]'); if (!d) return '';
    return d.getAttribute('aria-describedby').split(' ').map(i => txt(document.getElementById(i))).filter(Boolean).join(' ').slice(0, 500);
  };
  // The list of options an ARIA radio or checkbox sits in, one per list item, e.g. Google Forms checkboxes.
  // null for anything else, such as a row of a grid question.
  const optionList = el => {
    const item = el.closest('[role=listitem]');
    return item && item.querySelectorAll('[role=radio],[role=checkbox]').length === 1
      ? item.parentElement.closest('[role=list]') : null;
  };
  // The question from markup that names it: a legend or a labelled group. '' if there is none.
  const namedQuestion = el => {
    const fs = el.closest('fieldset'); if (fs && fs.querySelector('legend')) return txt(fs.querySelector('legend'));
    for (const grp of [el.closest('[role=radiogroup],[role=group],[role=listitem]'), optionList(el)]) {
      if (!grp) continue;
      const lb = grp.getAttribute('aria-labelledby');
      if (lb) { const e = document.getElementById(lb.split(' ')[0]); if (e) return txt(e); }
      if (grp.getAttribute('aria-label')) return grp.getAttribute('aria-label');
      const h = grp.querySelector('[role=heading],h1,h2,h3,h4,legend'); if (h) return txt(h);
    }
    return '';
  };
  // MathML as plain text, keeping the structure that concatenation loses: 1/4 must not read as 14.
  const mathText = e => {
    const kids = [...e.children].map(mathText);
    switch (e.tagName.toLowerCase()) {
      case 'mfrac': return `(${kids[0]})/(${kids[1]})`;
      case 'msup': return `${kids[0]}^(${kids[1]})`;
      case 'msub': return `${kids[0]}_${kids[1]}`;
      case 'msqrt': return `sqrt(${kids.join('')})`;
      case 'mroot': return `root${kids[1]}(${kids[0]})`;
      case 'annotation': case 'annotation-xml': return '';
    }
    return e.children.length ? kids.join('') : e.textContent.trim();
  };
  // Everything that answers a question: form inputs, ARIA radios and checkboxes, and answer tiles.
  const inputsIn = el => el.querySelectorAll('input, select, textarea, [role=radio], [role=checkbox], [data-jev-tile]');
  // Most quiz pages don't name the question in markup. Find its block instead: the largest ancestor
  // that holds this group's inputs and no others. Then split the block's visible text into pieces,
  // one per block-level element (a table stays whole), leaving out the options and any links or buttons.
  // A formula is read whole from its MathML, since MathJax draws the visible copy with CSS and has no text.
  const questionBlock = (group, i) => {
    let block = group[0].parentElement;
    while (!group.every(g => block.contains(g))) block = block.parentElement;
    while (block.parentElement && block.parentElement !== document.body
           && [...inputsIn(block.parentElement)].every(e => group.includes(e) || !vis(e))) block = block.parentElement;
    // An option's tile: the largest ancestor holding only that option's input.
    const tiles = group.map(g => {
      let t = g; while (t.parentElement !== block && inputsIn(t.parentElement).length === 1) t = t.parentElement; return t;
    });
    const skip = n => tiles.some(t => t.contains(n)) || group.some(g => [...(g.labels || [])].some(l => l.contains(n)))
      || n.parentElement.closest('a, button, [role=button], script, style, noscript')
      || (n.parentElement.closest('mjx-container') && !n.parentElement.closest('math'));  // MathJax glyphs; the MathML copy is read instead
    const shown = el => el.checkVisibility ? el.checkVisibility({checkOpacity: true, checkVisibilityCSS: true}) : vis(el);
    const pieces = new Map(), maths = new Set();
    const walk = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
    for (let n; (n = walk.nextNode());) {
      let s = n.textContent.replace(/\s+/g, ' ');
      if (!s.trim() || skip(n)) continue;
      const math = n.parentElement.closest('math');
      const holder = math ? (math.closest('mjx-container') || math).parentElement : n.parentElement;
      if (!shown(holder) || maths.has(math)) continue;  // MathJax hides the MathML itself, so check what holds it
      if (math) { maths.add(math); s = ' ' + mathText(math) + ' '; }
      let b = holder;
      while (b !== block && /^(inline|table-(cell|row))/.test(getComputedStyle(b).display)) b = b.parentElement;
      pieces.set(b, (pieces.get(b) || '') + s);
    }
    block.setAttribute('data-jev-block', i);
    return {block: `[data-jev-block="${i}"]`,
            pieces: [...pieces.values()].map(s => s.replace(/\s+/g, ' ').trim()).filter(Boolean).slice(0, 40).map(s => s.slice(0, 1000))};
  };
  document.querySelectorAll('[data-jev-block]').forEach(e => e.removeAttribute('data-jev-block'));
  // An id that stays with the element across reads, so a redrawn label doesn't look like a new field.
  const idOf = el => {
    if (!el.hasAttribute('data-jev')) el.setAttribute('data-jev', window.__jevIds = (window.__jevIds || 0) + 1);
    return el.getAttribute('data-jev');
  };
  const fields = [], groups = {};
  const addOption = (key, kind, el, option) => {
    let f = fields.find(x => x.key === key);
    if (!f) { f = {key, kind, question: namedQuestion(el), options: []}; fields.push(f); groups[key] = []; }
    f.options.push(option);
    groups[key].push(el);
  };
  document.querySelectorAll('input, select, textarea').forEach(el => {
    if (!vis(el) || el.disabled) return;
    const t = (el.type || '').toLowerCase();
    if (['hidden','submit','button','reset','image','file','password'].includes(t)) return;
    const id = idOf(el);
    const sel = `[data-jev="${id}"]`;
    if (t === 'radio' || t === 'checkbox') {
      addOption(t + ':' + (el.name || id), t, el, {label: labelFor(el), sel});
    } else if (el.tagName === 'SELECT') {
      fields.push({key: 'select:' + id, kind: 'select', question: namedQuestion(el) || labelFor(el), sel,
        options: [...el.options].filter(o => o.value).map(o => ({label: o.text.trim(), value: o.value}))});
    } else {
      fields.push({key: 'text:' + id, kind: 'text', question: labelFor(el), sel, filled: !!el.value,
        multiline: el.tagName === 'TEXTAREA'});
    }
  });
  // ARIA radios and checkboxes, e.g. Google Forms. They act like inputs, so they're read the same way.
  document.querySelectorAll('[role=radio], [role=checkbox]').forEach(el => {
    if (!vis(el) || el.getAttribute('aria-disabled') === 'true' || el.querySelector('input')) return;
    const kind = el.getAttribute('role'), id = idOf(el);
    const grp = el.closest('[role=radiogroup], [role=group], [role=listbox]') || optionList(el) || el.parentElement;
    addOption(`aria-${kind}:${idOf(grp)}`, kind, el,
              {label: el.getAttribute('aria-label') || txt(el), sel: `[data-jev="${id}"]`});
  });
  // ARIA dropdowns, e.g. Google Forms. An option with an empty value is a placeholder, such as "Choose".
  document.querySelectorAll('[role=listbox]').forEach(el => {
    if (!vis(el) || el.getAttribute('aria-disabled') === 'true') return;
    const options = [...el.querySelectorAll('[role=option]')]
      .filter(o => o.getAttribute('data-value') !== '' && o.getAttribute('aria-disabled') !== 'true');
    if (options.length < 2) return;
    const id = idOf(el);
    fields.push({key: 'aria-select:' + id, kind: 'select', question: namedQuestion(el) || labelFor(el),
      sel: `[data-jev="${id}"]`,
      options: options.map(o => ({label: txt(o) || o.getAttribute('aria-label') || '', sel: `[data-jev="${idOf(o)}"]`}))});
  });
  // Answer tiles: sibling elements styled as clickable, with short text and no inputs, e.g. JetPunk.
  // Only on pages without radio or checkbox groups, since menus and buttons look the same. Jev then
  // decides which groups are quiz questions.
  if (!fields.some(f => f.kind === 'radio' || f.kind === 'checkbox')) {
    const pointer = e => e && getComputedStyle(e).cursor === 'pointer';
    const tiles = [...document.body.querySelectorAll('div, li, span, button, a, label')].filter(e => {
      if (!vis(e) || !pointer(e) || pointer(e.parentElement) || e.querySelector('input, select, textarea')) return false;
      if (e.closest('nav, header, footer, [role=navigation], [role=banner], [role=dialog], [role=listbox]')) return false;
      // A plain link leads away. One with a #fragment or javascript: is usually handled in the page (Merriam-Webster).
      if (e.tagName === 'A' && e.getAttribute('href') && !/#|^javascript:/.test(e.getAttribute('href'))) return false;
      const t = txt(e); return t && t.length <= 150;
    });
    const byGroup = new Map();
    tiles.forEach(e => {
      let g = e.parentElement;  // the nearest ancestor holding another tile
      while (g !== document.body && !tiles.some(o => o !== e && g.contains(o))) g = g.parentElement;
      if (g !== document.body) byGroup.set(g, [...(byGroup.get(g) || []), e]);
    });
    byGroup.forEach((members, g) => {
      if (members.length < 2 || members.length > 8) return;
      members.forEach(e => {
        e.setAttribute('data-jev-tile', '');
        // Its tag and classes, numbers dropped ("choice choice-2"), so a Next button among the tiles stands out.
        const look = e.tagName + ' ' + (e.getAttribute('class') || '').replace(/\d+/g, '');
        addOption('tile:' + idOf(g), 'radio', e, {label: txt(e), sel: `[data-jev="${idOf(e)}"]`, tile: true, look});
      });
    });
  }
  fields.forEach(f => {
    const el = groups[f.key] ? groups[f.key][0] : document.querySelector(f.sel);
    const hint = hintFor(el);
    if (hint) f.hint = hint;
    if (el.closest('[aria-required=true]')) f.required = true;  // e.g. a Google Forms grid: one tick per row
  });
  fields.forEach((f, i) => {
    if (f.question || !groups[f.key]) return;
    if (groups[f.key].length > 1) Object.assign(f, questionBlock(groups[f.key], i));
    f.question = (f.pieces || []).join(' ') || f.options[0].label;  // a lone checkbox: its label is the question
  });
  // Nearby text, so Jev can tell a quiz question from site controls: the closest ancestor that says
  // clearly more than the field itself, e.g. "Check the sections to include in your exam".
  fields.forEach(f => {
    let e = groups[f.key] ? groups[f.key][0] : document.querySelector(f.sel);
    const own = f.question.length + (f.options || []).reduce((n, o) => n + o.label.length, 0);
    while (e.parentElement && e.parentElement !== document.body && txt(e).length < own + 40) e = e.parentElement;
    f.context = txt(e).slice(0, 300);
  });
  return fields;
}
