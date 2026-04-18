/* Theme preference */
(function () {
    const root = document.documentElement;
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");

    function applyTheme() {
        const userTheme = root.dataset.userTheme || "system";
        root.dataset.theme = userTheme === "system"
            ? (mediaQuery.matches ? "dark" : "light")
            : userTheme;
    }

    applyTheme();

    if (typeof mediaQuery.addEventListener === "function") {
        mediaQuery.addEventListener("change", applyTheme);
    } else if (typeof mediaQuery.addListener === "function") {
        mediaQuery.addListener(applyTheme);
    }
})();

/* Bar charts */
function renderBars(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const dataset = JSON.parse(container.dataset.chart || "[]");
    const max = Math.max(...dataset.map((item) => item.total), 1);

    container.innerHTML = dataset.map((item) => {
        const label = (item.status || item.portal_name || "Unknown")
            .replaceAll("_", " ")
            .replace(/\b\w/g, (char) => char.toUpperCase());
        const width = (item.total / max) * 100;
        const pct = Math.round(width);

        return `
            <div class="bar">
                <div class="list-row" style="padding:0;border:none;">
                    <strong style="font-size:.82rem;color:var(--text)">${label}</strong>
                    <span style="font-size:.78rem;font-weight:700;color:var(--accent)">${item.total}</span>
                </div>
                <div class="bar-track">
                    <div class="bar-fill" style="width:${pct}%"></div>
                </div>
            </div>
        `;
    }).join("");
}

/* Funnel chart */
function renderFunnel(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const dataset = JSON.parse(container.dataset.chart || "[]");
    const max = Math.max(...dataset.map((item) => item.count), 1);

    container.innerHTML = dataset.map((item, index) => {
        const width = (item.count / max) * 100;
        const pct = Math.round(width);
        const colors = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6"];
        const color = colors[index % colors.length];

        return `
            <div class="funnel-stage">
                <div class="funnel-label">
                    <strong>${item.status}</strong>
                    <span class="funnel-count">${item.count}</span>
                </div>
                <div class="funnel-bar" style="background:${color};">
                    <div class="funnel-fill" style="width:${pct}%; background:${color};"></div>
                </div>
            </div>
        `;
    }).join("");
}

/* Mobile sidebar */
(function () {
    const sidebar = document.getElementById("sidebar");
    const overlay = document.getElementById("sidebar-overlay");
    const hamburger = document.getElementById("hamburger-btn");

    if (!sidebar || !hamburger || !overlay) return;

    function openSidebar() {
        sidebar.classList.add("open");
        overlay.classList.add("open");
        hamburger.setAttribute("aria-expanded", "true");
        hamburger.textContent = "X";
        document.body.style.overflow = "hidden";
    }

    function closeSidebar() {
        sidebar.classList.remove("open");
        overlay.classList.remove("open");
        hamburger.setAttribute("aria-expanded", "false");
        hamburger.textContent = "Menu";
        document.body.style.overflow = "";
    }

    hamburger.addEventListener("click", function () {
        if (sidebar.classList.contains("open")) {
            closeSidebar();
        } else {
            openSidebar();
        }
    });

    overlay.addEventListener("click", closeSidebar);

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && sidebar.classList.contains("open")) {
            closeSidebar();
        }
    });

    sidebar.querySelectorAll(".nav-links a").forEach(function (link) {
        link.addEventListener("click", function () {
            if (window.innerWidth <= 900) {
                closeSidebar();
            }
        });
    });
})();

/* Active nav link */
(function () {
    const currentPath = window.location.pathname;
    document.querySelectorAll(".nav-links a").forEach(function (link) {
        const href = link.getAttribute("href");
        if (href && href !== "/" && currentPath.startsWith(href)) {
            link.classList.add("active");
        }
    });
})();

renderBars("status-chart");
renderBars("portal-chart");
renderFunnel("funnel-chart");
