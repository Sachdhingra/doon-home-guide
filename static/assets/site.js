// Sends a GA4 event for WhatsApp, directions and HDE clicks (only when GA4 is configured).
document.addEventListener("click", function (e) {
  var a = e.target.closest("[data-track]");
  if (!a || typeof window.gtag !== "function") return;
  window.gtag("event", a.getAttribute("data-track"), {
    label: a.getAttribute("data-label") || "",
    page: location.pathname,
    link_url: a.href
  });
});
