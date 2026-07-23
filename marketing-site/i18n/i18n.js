/* ================================================================
 * Shared i18n runtime for every marketing page except index.html
 * (the landing page keeps its own inline copy). Drop-in usage:
 *
 *   <script src="/assets/i18n.js" defer></script>
 *
 * and mark translatable nodes with data-i18n / data-i18n-html /
 * data-i18n-attr="attr:key" / data-i18n-aria-label="key".
 *
 * The script injects its own language toggle (into a nav actions
 * container if one exists, otherwise a small floating button) and
 * its own styles, so a page needs no nav surgery. Locale files are
 * the same JSON under /locales/ used by the landing page; keys for
 * sub-pages live under the "page" namespace (page.<slug>.<key>).
 * ================================================================ */
(function i18n() {
  // Bumped on every content change so updated copy reaches users
  // without a hard refresh. Keep in sync with index.html.
  var LOCALE_VERSION = '20260605b';

  var SUPPORTED = ['en','de','fr','es','it','pt','nl','pl','cs','ru','bg','tr','sv','no','fi','da','ar','zh','ja','ko'];
  var LANG_NAMES = { en:'English', de:'Deutsch', fr:'Français', es:'Español', it:'Italiano', pt:'Português', nl:'Nederlands', pl:'Polski', cs:'Čeština', ru:'Русский', bg:'Български', tr:'Türkçe', sv:'Svenska', no:'Norsk', fi:'Suomi', da:'Dansk', ar:'العربية', zh:'中文', ja:'日本語', ko:'한국어' };
  var LANG_FLAGS = { en:'gb', de:'de', fr:'fr', es:'es', it:'it', pt:'pt', nl:'nl', pl:'pl', cs:'cz', ru:'ru', bg:'bg', tr:'tr', sv:'se', no:'no', fi:'fi', da:'dk', ar:'sa', zh:'cn', ja:'jp', ko:'kr' };
  var FLAG_URL = function (code) { return 'https://flagcdn.com/' + code + '.svg'; };
  var RTL = { ar: true };
  var COUNTRY_TO_LANG = {
    DE:'de', AT:'de', CH:'de', LI:'de',
    FR:'fr', BE:'fr', LU:'fr', MC:'fr',
    ES:'es', MX:'es', AR:'es', CL:'es', CO:'es', PE:'es', VE:'es', UY:'es', BO:'es', CR:'es', DO:'es', EC:'es', GT:'es', HN:'es', NI:'es', PA:'es', PY:'es',
    IT:'it', SM:'it', VA:'it',
    PT:'pt', BR:'pt', AO:'pt', MZ:'pt', CV:'pt',
    NL:'nl', PL:'pl', CZ:'cs', SK:'cs',
    RU:'ru', KZ:'ru', BY:'ru', KG:'ru',
    BG:'bg', TR:'tr', SE:'sv', NO:'no', FI:'fi',
    DK:'da', GL:'da', FO:'da',
    SA:'ar', AE:'ar', EG:'ar', QA:'ar', OM:'ar', KW:'ar', BH:'ar', JO:'ar', LB:'ar', IQ:'ar', YE:'ar', LY:'ar', TN:'ar', DZ:'ar', MA:'ar', SD:'ar', SY:'ar', PS:'ar', MR:'ar',
    CN:'zh', HK:'zh', MO:'zh', TW:'zh', SG:'zh',
    JP:'ja', KR:'ko'
  };
  var STORAGE_LANG = 'oce-lang';
  var STORAGE_MANUAL = 'oce-lang-manual';

  function get(obj, path) {
    return path.split('.').reduce(function (o, k) {
      return (o && o[k] != null) ? o[k] : null;
    }, obj);
  }

  function apply(dict) {
    document.querySelectorAll('[data-i18n]').forEach(function (el) {
      var val = get(dict, el.getAttribute('data-i18n'));
      if (val != null) el.textContent = val;
    });
    document.querySelectorAll('[data-i18n-html]').forEach(function (el) {
      var val = get(dict, el.getAttribute('data-i18n-html'));
      if (val != null) el.innerHTML = val;
    });
    document.querySelectorAll('[data-i18n-attr]').forEach(function (el) {
      // Format: "attr:dotted.key" (one pair; comma-separate for several).
      el.getAttribute('data-i18n-attr').split(',').forEach(function (pair) {
        var bits = pair.split(':');
        if (bits.length !== 2) return;
        var val = get(dict, bits[1].trim());
        if (val != null) el.setAttribute(bits[0].trim(), val);
      });
    });
    document.querySelectorAll('[data-i18n-aria-label]').forEach(function (el) {
      var val = get(dict, el.getAttribute('data-i18n-aria-label'));
      if (val != null) el.setAttribute('aria-label', val);
    });
    var lang = dict.__lang || 'en';
    document.querySelectorAll('.oi18n-code').forEach(function (el) { el.textContent = lang.toUpperCase(); });
    var flagEl = document.getElementById('oi18n-flag');
    if (flagEl) flagEl.src = FLAG_URL(LANG_FLAGS[lang] || 'gb');
    document.querySelectorAll('#oi18n-menu [data-set-lang]').forEach(function (btn) {
      btn.classList.toggle('is-current', btn.getAttribute('data-set-lang') === lang);
    });
  }

  function fetchLocale(lang) {
    return fetch('/locales/' + lang + '.json?v=' + LOCALE_VERSION, { cache: 'default' })
      .then(function (res) { if (!res.ok) throw 0; return res.json(); })
      .then(function (json) { json.__lang = lang; return json; })
      .catch(function () {
        if (lang !== 'en') return fetchLocale('en');
        return { __lang: 'en' };
      });
  }

  function setLang(lang, manual) {
    if (SUPPORTED.indexOf(lang) === -1) lang = 'en';
    return fetchLocale(lang).then(function (dict) {
      apply(dict);
      document.documentElement.lang = lang;
      document.documentElement.dir = RTL[lang] ? 'rtl' : 'ltr';
      try {
        localStorage.setItem(STORAGE_LANG, lang);
        if (manual) localStorage.setItem(STORAGE_MANUAL, '1');
      } catch (e) {}
      var url = new URL(location.href);
      if (lang === 'en') url.searchParams.delete('lang'); else url.searchParams.set('lang', lang);
      history.replaceState(null, '', url);
    });
  }

  function detectSync() {
    var urlLang = new URLSearchParams(location.search).get('lang');
    if (urlLang && SUPPORTED.indexOf(urlLang) !== -1) return { lang: urlLang, fromUrl: true };
    try {
      var stored = localStorage.getItem(STORAGE_LANG);
      if (stored && SUPPORTED.indexOf(stored) !== -1) return { lang: stored, stored: true };
    } catch (e) {}
    var navLang = (navigator.language || 'en').slice(0, 2).toLowerCase();
    if (SUPPORTED.indexOf(navLang) !== -1) return { lang: navLang };
    return { lang: 'en' };
  }

  function detectGeo() {
    return new Promise(function (resolve) {
      try {
        var ctrl = new AbortController();
        var t = setTimeout(function () { ctrl.abort(); }, 3000);
        fetch('https://ipwho.is/?fields=country_code', { signal: ctrl.signal })
          .then(function (r) { return r.json(); })
          .then(function (j) {
            clearTimeout(t);
            resolve(j && j.country_code && COUNTRY_TO_LANG[j.country_code] ? COUNTRY_TO_LANG[j.country_code] : null);
          })
          .catch(function () { resolve(null); });
      } catch (e) { resolve(null); }
    });
  }

  function injectStyles() {
    if (document.getElementById('oi18n-style')) return;
    var css = ''
      + '.oi18n-toggle{display:inline-flex;align-items:center;gap:7px;cursor:pointer;border:1px solid var(--line-2,rgba(15,23,42,.14));background:var(--card,#fff);color:var(--ink-1,#1e293b);border-radius:8px;padding:6px 10px;font:inherit;font-size:13px;line-height:1;transition:border-color .15s,box-shadow .15s;}'
      + '.oi18n-toggle:hover{border-color:var(--accent,#0284c7);}'
      + '.oi18n-toggle img{display:block;border-radius:2px;}'
      + '.oi18n-code{font-weight:600;letter-spacing:.02em;}'
      + '.oi18n-float{position:fixed;top:14px;right:14px;z-index:2147483000;box-shadow:0 4px 16px rgba(2,8,23,.12);}'
      + '#oi18n-menu{position:fixed;z-index:2147483001;max-height:70vh;overflow:auto;background:var(--card,#fff);border:1px solid var(--line-2,rgba(15,23,42,.14));border-radius:12px;box-shadow:0 12px 40px rgba(2,8,23,.22);padding:6px;min-width:210px;}'
      + '#oi18n-menu[hidden]{display:none;}'
      + '#oi18n-menu button{display:flex;align-items:center;gap:10px;width:100%;text-align:left;background:none;border:0;border-radius:8px;padding:8px 10px;cursor:pointer;color:var(--ink-1,#1e293b);font:inherit;font-size:13.5px;}'
      + '#oi18n-menu button:hover{background:var(--accent,#0284c7);color:#fff;}'
      + '#oi18n-menu button.is-current{background:rgba(2,132,199,.12);}'
      + '#oi18n-menu button:hover.is-current{color:#fff;}'
      + '#oi18n-menu .oi18n-menu-code{font-weight:600;width:26px;flex:0 0 auto;}'
      + '#oi18n-menu .oi18n-menu-name{color:var(--ink-2,#475569);}'
      + '#oi18n-menu button:hover .oi18n-menu-name{color:rgba(255,255,255,.85);}'
      + '#oi18n-menu img{flex:0 0 auto;border-radius:2px;}';
    var st = document.createElement('style');
    st.id = 'oi18n-style';
    st.textContent = css;
    document.head.appendChild(st);
  }

  function buildToggle() {
    if (document.getElementById('oi18n-toggle')) return;
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'oi18n-toggle';
    btn.id = 'oi18n-toggle';
    btn.setAttribute('aria-label', 'Change language');
    btn.setAttribute('title', 'Change language');
    btn.innerHTML = '<img id="oi18n-flag" src="' + FLAG_URL('gb') + '" width="20" height="15" alt="" loading="eager" decoding="async" /><span class="oi18n-code">EN</span>';

    // Prefer an existing nav actions container so the toggle sits in
    // the header; otherwise float it in the top-right corner.
    var host = document.querySelector('.nav-right, .nav-links, .nav-actions, .nav-cta');
    if (host) {
      host.appendChild(btn);
    } else {
      btn.classList.add('oi18n-float');
      document.body.appendChild(btn);
    }

    var menu = document.createElement('div');
    menu.id = 'oi18n-menu';
    menu.hidden = true;
    menu.setAttribute('role', 'menu');
    menu.setAttribute('aria-label', 'Language');
    menu.innerHTML = SUPPORTED.map(function (l) {
      return '<button type="button" role="menuitem" data-set-lang="' + l + '">'
        + '<img src="' + FLAG_URL(LANG_FLAGS[l]) + '" width="20" height="15" alt="" loading="lazy" decoding="async" />'
        + '<span class="oi18n-menu-code">' + l.toUpperCase() + '</span>'
        + '<span class="oi18n-menu-name">' + LANG_NAMES[l] + '</span></button>';
    }).join('');
    document.body.appendChild(menu);

    function openMenu() {
      var r = btn.getBoundingClientRect();
      menu.style.top = (r.bottom + 8) + 'px';
      menu.style.right = Math.max(12, window.innerWidth - r.right) + 'px';
      menu.hidden = false;
    }
    function closeMenu() { menu.hidden = true; }

    document.addEventListener('click', function (e) {
      if (e.target.closest('#oi18n-toggle')) {
        e.preventDefault();
        if (menu.hidden) openMenu(); else closeMenu();
        return;
      }
      var opt = e.target.closest('[data-set-lang]');
      if (opt) {
        e.preventDefault();
        setLang(opt.getAttribute('data-set-lang'), true);
        closeMenu();
        return;
      }
      if (!e.target.closest('#oi18n-menu')) closeMenu();
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeMenu(); });
    window.addEventListener('resize', closeMenu, { passive: true });
  }

  function boot() {
    injectStyles();
    buildToggle();
    var det = detectSync();
    setLang(det.lang, det.fromUrl);
    if (!det.fromUrl) {
      try {
        if (!localStorage.getItem(STORAGE_MANUAL)) {
          detectGeo().then(function (geo) { if (geo && geo !== det.lang) setLang(geo, false); });
        }
      } catch (e) {}
    }
    window.__oceI18n = { setLang: setLang, SUPPORTED: SUPPORTED };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
