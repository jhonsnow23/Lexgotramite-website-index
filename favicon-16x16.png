
document.addEventListener("DOMContentLoaded", function () {
  if (localStorage.getItem("cookiesAccepted") === "true") return;

  const banner = document.createElement("div");
  banner.id = "cookie-banner";
  banner.innerHTML = `
    <div style="position:fixed;left:0;right:0;bottom:0;z-index:9999;background:#0f172a;color:#fff;padding:16px;border-top:1px solid rgba(255,255,255,.12);font-family:Arial,sans-serif;">
      <div style="max-width:1100px;margin:0 auto;display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap;">
        <div style="font-size:14px;line-height:1.5;">
          Usamos cookies técnicas y, en su caso, de análisis para mejorar la experiencia del usuario.
          Puedes obtener más información en nuestra <a href="privacidad.html" style="color:#c7d2fe;text-decoration:underline;">Política de privacidad</a>.
        </div>
        <button id="accept-cookies-btn" style="background:#4338ca;color:#fff;border:none;border-radius:8px;padding:10px 16px;font-weight:600;cursor:pointer;">
          Aceptar
        </button>
      </div>
    </div>
  `;
  document.body.appendChild(banner);

  const btn = document.getElementById("accept-cookies-btn");
  btn.addEventListener("click", function () {
    localStorage.setItem("cookiesAccepted", "true");
    const existing = document.getElementById("cookie-banner");
    if (existing) existing.remove();
  });
});
