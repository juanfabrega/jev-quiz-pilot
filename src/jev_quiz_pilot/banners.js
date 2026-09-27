// Finds consent and cookie buttons ("I understand", "Accept all", ...) in pop-ups or pinned banners.
// Marks them with data-jev-dismiss and returns how many it found. Only looks inside dialogs and
// fixed or sticky elements, so it won't press a quiz's own buttons.
() => {
  const RE = /^\s*(i understand|i accept|accept( all)?( cookies)?|allow( all)?( cookies)?|i agree|agree( and close)?|got it|ok(ay)?)\s*$/i;
  const pinned = el => {
    for (let e = el; e && e !== document.body; e = e.parentElement) {
      if (e.matches('[role=dialog],[role=alertdialog],[aria-modal=true]')) return true;
      const p = getComputedStyle(e).position;
      if (p === 'fixed' || p === 'sticky') return true;
    }
    return false;
  };
  let n = 0;
  document.querySelectorAll('button, [role=button], a').forEach(b => {
    if (b.offsetWidth && RE.test(b.innerText || '') && pinned(b)) { b.setAttribute('data-jev-dismiss', ''); n++; }
  });
  return n;
}
