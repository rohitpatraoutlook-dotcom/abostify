(() => {
  "use strict";
  const root = document.documentElement;
  const saved = localStorage.getItem("abostify-theme");
  if (saved === "dark" || saved === "light") root.dataset.theme = saved;

  const theme = document.createElement("button");
  theme.type = "button";
  theme.className = "ui-theme-toggle";
  theme.setAttribute("aria-label", "Toggle color theme");
  theme.title = "Toggle light/dark mode";
  const drawTheme = () => {
    theme.textContent = root.dataset.theme === "dark" ? "☀" : "☾";
    theme.setAttribute("aria-label",
      root.dataset.theme === "dark" ? "Switch to light mode" : "Switch to dark mode");
  };
  theme.addEventListener("click", () => {
    root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem("abostify-theme", root.dataset.theme);
    drawTheme();
  });
  drawTheme();
  document.body.appendChild(theme);

  const headerLinks = [...document.querySelectorAll(".nav-links a[href]")];
  const candidates = [
    {match: /home/i, icon: "⌂", label: "Home"},
    {match: /social feed|^feed$/i, icon: "◉", label: "Feed"},
    {match: /discover people|search people/i, icon: "◎", label: "Discover"},
    {match: /create post/i, icon: "+", label: "Create"},
    {match: /my profile/i, icon: "○", label: "Profile"},
    {match: /dashboard/i, icon: "▦", label: "Dashboard"}
  ];
  const links = [];
  for (const item of candidates) {
    const found = headerLinks.find(a => item.match.test(a.textContent.trim()));
    if (found && !links.some(x => x.href === found.href)) {
      links.push({href: found.href, icon: item.icon, label: item.label});
    }
  }
  if (links.length) {
    const nav = document.createElement("nav");
    nav.className = "ui-mobile-nav";
    nav.setAttribute("aria-label", "Mobile navigation");
    const current = location.pathname.replace(/\/+$/, "") || "/";
    links.slice(0, 5).forEach(item => {
      const a = document.createElement("a");
      a.href = item.href;
      const target = new URL(item.href, location.origin).pathname.replace(/\/+$/, "") || "/";
      if (target === current) {
        a.classList.add("active");
        a.setAttribute("aria-current", "page");
      }
      const icon = document.createElement("span");
      icon.setAttribute("aria-hidden", "true");
      icon.textContent = item.icon;
      a.append(icon, document.createTextNode(item.label));
      nav.appendChild(a);
    });
    document.body.appendChild(nav);
  }

  document.querySelectorAll('a[href="#"]').forEach(a => {
    a.addEventListener("click", e => e.preventDefault());
  });
})();
