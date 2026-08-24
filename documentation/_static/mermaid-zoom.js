(function () {
    "use strict";

    const MIN_SCALE = 0.4;
    const MAX_SCALE = 4;
    const SCALE_STEP = 1.2;

    function clamp(value, min, max) {
        return Math.min(max, Math.max(min, value));
    }

    function mermaidSvgs() {
        return Array.from(document.querySelectorAll(".mermaid svg, svg[id^='mermaid-']"));
    }

    function enhance(svg) {
        if (svg.dataset.zoomEnhanced === "true" || svg.closest(".mermaid-zoom")) {
            return;
        }

        svg.dataset.zoomEnhanced = "true";

        const shell = document.createElement("div");
        shell.className = "mermaid-zoom";

        const toolbar = document.createElement("div");
        toolbar.className = "mermaid-zoom__toolbar";

        const viewport = document.createElement("div");
        viewport.className = "mermaid-zoom__viewport";
        viewport.setAttribute("role", "region");
        viewport.setAttribute("aria-label", "Zoomable Mermaid diagram");

        const buttons = [
            ["+", "Zoom in"],
            ["-", "Zoom out"],
            ["Reset", "Reset zoom"],
        ];

        const [zoomInButton, zoomOutButton, resetButton] = buttons.map(([text, label]) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "mermaid-zoom__button";
            button.textContent = text;
            button.title = label;
            button.setAttribute("aria-label", label);
            toolbar.appendChild(button);
            return button;
        });

        svg.parentNode.insertBefore(shell, svg);
        shell.appendChild(toolbar);
        shell.appendChild(viewport);
        viewport.appendChild(svg);

        let scale = 1;
        let x = 0;
        let y = 0;
        let dragging = false;
        let lastX = 0;
        let lastY = 0;

        function applyTransform() {
            svg.style.transform = `translate(${x}px, ${y}px) scale(${scale})`;
        }

        function zoomAt(nextScale, clientX, clientY) {
            const rect = viewport.getBoundingClientRect();
            const oldScale = scale;
            scale = clamp(nextScale, MIN_SCALE, MAX_SCALE);

            const offsetX = clientX - rect.left;
            const offsetY = clientY - rect.top;
            x = offsetX - ((offsetX - x) * scale) / oldScale;
            y = offsetY - ((offsetY - y) * scale) / oldScale;
            applyTransform();
        }

        function reset() {
            scale = 1;
            x = 0;
            y = 0;
            applyTransform();
        }

        zoomInButton.addEventListener("click", () => {
            const rect = viewport.getBoundingClientRect();
            zoomAt(scale * SCALE_STEP, rect.left + rect.width / 2, rect.top + rect.height / 2);
        });

        zoomOutButton.addEventListener("click", () => {
            const rect = viewport.getBoundingClientRect();
            zoomAt(scale / SCALE_STEP, rect.left + rect.width / 2, rect.top + rect.height / 2);
        });

        resetButton.addEventListener("click", reset);
        viewport.addEventListener("dblclick", reset);

        viewport.addEventListener(
            "wheel",
            (event) => {
                event.preventDefault();
                const factor = event.deltaY < 0 ? SCALE_STEP : 1 / SCALE_STEP;
                zoomAt(scale * factor, event.clientX, event.clientY);
            },
            { passive: false }
        );

        viewport.addEventListener("pointerdown", (event) => {
            dragging = true;
            lastX = event.clientX;
            lastY = event.clientY;
            viewport.setPointerCapture(event.pointerId);
        });

        viewport.addEventListener("pointermove", (event) => {
            if (!dragging) {
                return;
            }
            x += event.clientX - lastX;
            y += event.clientY - lastY;
            lastX = event.clientX;
            lastY = event.clientY;
            applyTransform();
        });

        viewport.addEventListener("pointerup", () => {
            dragging = false;
        });

        viewport.addEventListener("pointercancel", () => {
            dragging = false;
        });

        applyTransform();
    }

    function enhanceAll() {
        mermaidSvgs().forEach(enhance);
    }

    document.addEventListener("DOMContentLoaded", () => {
        enhanceAll();
        setTimeout(enhanceAll, 300);
        setTimeout(enhanceAll, 1000);

        const observer = new MutationObserver(enhanceAll);
        observer.observe(document.body, { childList: true, subtree: true });
    });
})();
