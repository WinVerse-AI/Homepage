const header = document.querySelector("[data-header]");
const menuToggle = document.querySelector("[data-menu-toggle]");
const navigation = document.querySelector("[data-nav]");
const year = document.querySelector("[data-year]");
const navGroup = document.querySelector("[data-nav-group]");
const submenuToggle = document.querySelector("[data-submenu-toggle]");
const contactForm = document.querySelector("[data-contact-form]");

if (year) {
  year.textContent = new Date().getFullYear();
}

const updateHeader = () => {
  header?.classList.toggle("is-scrolled", window.scrollY > 24);
};

updateHeader();
window.addEventListener("scroll", updateHeader, { passive: true });

const closeMenu = () => {
  navigation?.classList.remove("is-open");
  menuToggle?.setAttribute("aria-expanded", "false");
  menuToggle?.setAttribute("aria-label", "Open navigation");
  navGroup?.classList.remove("is-expanded");
  submenuToggle?.setAttribute("aria-expanded", "false");
  document.body.classList.remove("menu-open");
};

menuToggle?.addEventListener("click", () => {
  const isOpen = navigation?.classList.toggle("is-open") ?? false;
  menuToggle.setAttribute("aria-expanded", String(isOpen));
  menuToggle.setAttribute("aria-label", isOpen ? "Close navigation" : "Open navigation");
  document.body.classList.toggle("menu-open", isOpen);
});

navigation?.querySelectorAll("a").forEach((link) => {
  link.addEventListener("click", closeMenu);
});

submenuToggle?.addEventListener("click", () => {
  const isExpanded = navGroup?.classList.toggle("is-expanded") ?? false;
  submenuToggle.setAttribute("aria-expanded", String(isExpanded));
});

window.addEventListener("resize", () => {
  if (window.innerWidth > 980) closeMenu();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeMenu();
    menuToggle?.focus();
  }
});

document.addEventListener("click", (event) => {
  if (!navigation?.classList.contains("is-open")) return;
  const target = event.target;
  if (!(target instanceof Node)) return;
  if (!navigation.contains(target) && !menuToggle?.contains(target)) closeMenu();
});

if (contactForm instanceof HTMLFormElement) {
  const topicField = contactForm.elements.namedItem("topic");
  const requestedTopic = new URLSearchParams(window.location.search).get("topic");

  if (topicField instanceof HTMLSelectElement && requestedTopic === "partnership") {
    topicField.value = "Partnership";
  }

  contactForm.addEventListener("submit", (event) => {
    event.preventDefault();

    if (!contactForm.reportValidity()) return;

    const formData = new FormData(contactForm);
    const name = String(formData.get("name") || "").trim();
    const email = String(formData.get("email") || "").trim();
    const organisation = String(formData.get("organisation") || "").trim();
    const topic = String(formData.get("topic") || "General enquiry").trim();
    const message = String(formData.get("message") || "").trim();
    const subject = `WinVerse website enquiry — ${topic}`;
    const body = [
      "Hello WinVerse team,",
      "",
      message,
      "",
      "— Enquiry details —",
      `Name: ${name}`,
      `Email: ${email}`,
      `Organisation: ${organisation || "Not provided"}`,
      `Topic: ${topic}`,
    ].join("\n");
    const status = contactForm.querySelector("[data-form-status]");

    if (status) {
      status.textContent = "Your email application is opening with this enquiry addressed to WinVerse™. Review it, then press Send.";
    }

    window.location.href = `mailto:winverse.ai@gmail.com?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  });
}
