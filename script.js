(() => {
  const dictionaries = window.WINVERSE_I18N || {};
  const supported = ["en", "zh", "ja", "fr", "de", "es"];
  const langCodes = { en: "en", zh: "zh-CN", ja: "ja", fr: "fr", de: "de", es: "es" };
  const page = document.body.dataset.page || "home";

  const safeStoredLanguage = (() => {
    try {
      return window.localStorage.getItem("winverse-language");
    } catch {
      return null;
    }
  })();

  const browserLanguage = (navigator.language || "").slice(0, 2);
  let activeLanguage = supported.includes(safeStoredLanguage)
    ? safeStoredLanguage
    : supported.includes(browserLanguage)
      ? browserLanguage
      : "en";

  const t = (key) => {
    return dictionaries[activeLanguage]?.[key] ?? dictionaries.en?.[key] ?? key;
  };

  const activeAttr = (name) => (page === name ? ' aria-current="page"' : "");
  const platformActive = page === "platform" || page === "serotonix";

  const headerHost = document.querySelector("[data-site-header]");
  if (headerHost) {
    headerHost.innerHTML = [
      '<header class="site-header" data-header>',
      '<div class="shell header-grid">',
      '<a class="brand" href="index.html" aria-label="WinVerse home">',
      '<img class="brand-logo" src="assets/winverse-logo-full.png" alt="WinVerse™">',
      '<span class="brand-locations" data-i18n="brand.locations"></span>',
      '</a>',
      '<button class="menu-toggle" type="button" aria-expanded="false" aria-controls="site-nav" data-menu-toggle>',
      '<span class="menu-toggle-label">Menu</span>',
      '<span class="menu-toggle-icon" aria-hidden="true"><i></i><i></i></span>',
      '</button>',
      '<nav class="site-nav" id="site-nav" aria-label="Main navigation" data-nav>',
      '<a href="index.html"' + activeAttr("home") + ' data-i18n="nav.home"></a>',
      '<div class="nav-group' + (platformActive ? " is-current" : "") + '" data-nav-group>',
      '<div class="nav-group-row">',
      '<a href="platform.html"' + activeAttr("platform") + ' data-i18n="nav.platform"></a>',
      '<button class="submenu-toggle" type="button" aria-expanded="false" aria-controls="platform-menu" data-submenu-toggle>',
      '<span class="sr-only" data-i18n="nav.platformMenu"></span><span aria-hidden="true">⌄</span>',
      '</button></div>',
      '<div class="nav-submenu" id="platform-menu">',
      '<a href="serotonix.html"' + activeAttr("serotonix") + ' data-i18n="nav.serotonix"></a>',
      '</div></div>',
      '<a href="evidence.html"' + activeAttr("evidence") + ' data-i18n="nav.evidence"></a>',
      '<a href="company.html"' + activeAttr("company") + ' data-i18n="nav.company"></a>',
      '<a href="about.html"' + activeAttr("about") + ' data-i18n="nav.about"></a>',
      '<a class="nav-contact" href="contact.html"' + activeAttr("contact") + ' data-i18n="nav.contact"></a>',
      '<label class="language-control">',
      '<span class="sr-only" data-i18n="language.label"></span>',
      '<span aria-hidden="true">◌</span>',
      '<select data-language-select aria-label="Language">',
      '<option value="en">English</option>',
      '<option value="zh">中文</option>',
      '<option value="ja">日本語</option>',
      '<option value="fr">Français</option>',
      '<option value="de">Deutsch</option>',
      '<option value="es">Español</option>',
      '</select></label></nav></div></header>'
    ].join("");
  }

  const footerHost = document.querySelector("[data-site-footer]");
  if (footerHost) {
    footerHost.innerHTML = [
      '<footer class="site-footer"><div class="shell footer-grid">',
      '<span data-i18n="footer.status"></span>',
      '<span class="footer-cities" data-i18n="brand.locations"></span>',
      '<a href="mailto:winverse.ai@gmail.com" data-i18n="footer.contact"></a>',
      '</div></footer>'
    ].join("");
  }

  const translatePage = (language) => {
    activeLanguage = supported.includes(language) ? language : "en";
    document.documentElement.lang = langCodes[activeLanguage];
    document.documentElement.dataset.language = activeLanguage;

    document.querySelectorAll("[data-i18n]").forEach((node) => {
      node.textContent = t(node.dataset.i18n);
    });

    document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
      node.setAttribute("placeholder", t(node.dataset.i18nPlaceholder));
    });

    document.querySelectorAll("[data-i18n-alt]").forEach((node) => {
      node.setAttribute("alt", t(node.dataset.i18nAlt));
    });

    const title = dictionaries[activeLanguage]?.[page + ".metaTitle"];
    const description = dictionaries[activeLanguage]?.[page + ".metaDescription"];
    if (title) document.title = title;
    if (description) {
      document.querySelector('meta[name="description"]')?.setAttribute("content", description);
    }

    document.querySelectorAll("[data-language-select]").forEach((select) => {
      select.value = activeLanguage;
      select.setAttribute("aria-label", t("language.label"));
    });

    try {
      window.localStorage.setItem("winverse-language", activeLanguage);
    } catch {
      // Translation works without persistent storage.
    }
  };

  translatePage(activeLanguage);

  document.querySelectorAll("[data-language-select]").forEach((select) => {
    select.addEventListener("change", (event) => translatePage(event.target.value));
  });

  const menuToggle = document.querySelector("[data-menu-toggle]");
  const navigation = document.querySelector("[data-nav]");

  const closeNavigation = () => {
    navigation?.classList.remove("is-open");
    menuToggle?.setAttribute("aria-expanded", "false");
    document.body.classList.remove("nav-open");
  };

  menuToggle?.addEventListener("click", () => {
    const isOpen = navigation?.classList.toggle("is-open");
    menuToggle.setAttribute("aria-expanded", String(Boolean(isOpen)));
    document.body.classList.toggle("nav-open", Boolean(isOpen));
  });

  document.querySelectorAll("[data-submenu-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const expanded = button.getAttribute("aria-expanded") === "true";
      button.setAttribute("aria-expanded", String(!expanded));
      button.closest("[data-nav-group]")?.classList.toggle("is-expanded", !expanded);
    });
  });

  document.querySelectorAll(".site-nav a").forEach((link) => {
    link.addEventListener("click", closeNavigation);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeNavigation();
  });

  const header = document.querySelector("[data-header]");
  const updateHeader = () => header?.classList.toggle("is-scrolled", window.scrollY > 8);
  updateHeader();
  window.addEventListener("scroll", updateHeader, { passive: true });

  document.querySelectorAll("[data-dialog-open]").forEach((button) => {
    button.addEventListener("click", () => {
      const dialog = document.getElementById(button.dataset.dialogOpen);
      if (dialog?.showModal) dialog.showModal();
    });
  });

  document.querySelectorAll("dialog").forEach((dialog) => {
    dialog.querySelectorAll("[data-dialog-close]").forEach((button) => {
      button.addEventListener("click", () => dialog.close());
    });
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
  });

  document.querySelectorAll("img[data-image-fallback]").forEach((image) => {
    const showFallback = () => {
      image.hidden = true;
      image.nextElementSibling?.removeAttribute("hidden");
    };
    image.addEventListener("error", showFallback);
    if (image.complete && image.naturalWidth === 0) showFallback();
  });

  const contactForm = document.querySelector("[data-contact-form]");
  contactForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    const data = new FormData(contactForm);
    const interestSelect = contactForm.querySelector('[name="interest"]');
    const interest = interestSelect?.selectedOptions?.[0]?.textContent || "";
    const subject = t("contact.subject") + " — " + interest;
    const body = [
      t("contact.name") + ": " + (data.get("name") || ""),
      t("contact.email") + ": " + (data.get("email") || ""),
      t("contact.organisation") + ": " + (data.get("organisation") || ""),
      t("contact.interest") + ": " + interest,
      "",
      t("contact.message") + ":",
      data.get("message") || ""
    ].join("\n");

    const status = contactForm.querySelector("[data-form-status]");
    if (status) status.textContent = t("contact.ready");
    window.location.href = "mailto:winverse.ai@gmail.com?subject=" + encodeURIComponent(subject) + "&body=" + encodeURIComponent(body);
  });

  const query = new URLSearchParams(window.location.search);
  if (contactForm && query.get("topic")) {
    const select = contactForm.querySelector('[name="interest"]');
    const requested = query.get("topic");
    if (select && [...select.options].some((option) => option.value === requested)) {
      select.value = requested;
    }
  }
})();
