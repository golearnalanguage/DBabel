/* Desktop-only presentation. Review state and document text are unchanged. */
(() => {
  const params = new URLSearchParams(window.location.search);
  if (params.get('desktop') !== 'macos') return;
  document.documentElement.classList.add('desktop-macos');
  const accent = params.get('accent');
  if (/^#[0-9a-fA-F]{6}$/.test(accent || '')) {
    document.documentElement.style.setProperty('--mac-accent', accent);
  }
})();
