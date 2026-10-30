/* Boot: theme, seed conversations, first tab from the URL hash. */
(function () {
  try {
    var t = localStorage.getItem('gs-theme');
    if (t && t !== 'system') document.documentElement.setAttribute('data-theme', t);
    if (t) document.querySelectorAll('[data-theme-opt]').forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.themeOpt === t ? 'true' : 'false'); });
  } catch (e) { /* storage blocked: follow the system theme */ }
  var q = new URLSearchParams(location.search).get('theme');
  if (q === 'dark' || q === 'light') document.documentElement.setAttribute('data-theme', q);
  document.getElementById('tb-date').textContent = U.wd(U.today) + ', ' + U.d(U.today);
  CHAT.init();
  U.badges();
  U.tab((location.hash || '#tro-ly').slice(1));
  window.addEventListener('hashchange', function () { U.tab(location.hash.slice(1)); });
})();
