"""Banner de aviso de cookies, persistente en localStorage.

Se renderiza como un iframe invisible (height=0) cuyo JS inyecta el banner en
el documento padre (la página de Streamlit), no en el iframe del componente.
Esto permite que la barra se vea anclada al borde inferior de TODA la app y
no solo de la celda del componente.

Uso típico (en `home.py`, justo después de `set_page_config`):

    from components.cookie_banner import render_cookie_banner
    render_cookie_banner()

Una vez el usuario hace click en "Entendido", se guarda
`ptar-cookie-consent-v1=true` en `localStorage` del navegador, así no vuelve
a mostrarse en próximas visitas (ni en reruns dentro de la misma sesión).
"""
from __future__ import annotations

from streamlit.components.v1 import html as components_html


_BANNER_SCRIPT = """
<script>
(function() {
  const KEY = 'ptar-cookie-consent-v1';
  const BANNER_ID = 'ptar-cookie-banner';

  // Acceso al documento/localStorage del padre (Streamlit nos pone en iframe).
  let parentDoc, parentStorage;
  try {
    parentDoc = window.parent.document;
    parentStorage = window.parent.localStorage;
  } catch (e) {
    return; // sandbox cross-origin: no podemos hacer nada
  }

  // Ya consintió → no mostrar.
  if (parentStorage.getItem(KEY) === 'true') return;

  // Ya inyectado en un rerun previo → no duplicar.
  if (parentDoc.getElementById(BANNER_ID)) return;

  // ── Estilo ─────────────────────────────────────────────────────────────
  const style = parentDoc.createElement('style');
  style.textContent = `
    #${BANNER_ID} {
      position: fixed;
      bottom: 0; left: 0; right: 0;
      background: #185FA5;
      color: white;
      padding: 12px 22px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
      font-size: 13px;
      line-height: 1.4;
      z-index: 100000;
      box-shadow: 0 -2px 10px rgba(0,0,0,0.18);
    }
    #${BANNER_ID} .ptar-cookie-text { flex: 1 1 auto; min-width: 0; }
    #${BANNER_ID} .ptar-cookie-text strong {
      display: block; margin-bottom: 2px; font-size: 14px;
    }
    #${BANNER_ID} button {
      background: white;
      color: #185FA5;
      border: none;
      padding: 8px 20px;
      border-radius: 6px;
      font-weight: 700;
      cursor: pointer;
      font-size: 13px;
      white-space: nowrap;
      flex: 0 0 auto;
      transition: background 0.15s ease;
    }
    #${BANNER_ID} button:hover { background: #E8F0F8; }
    @media (max-width: 640px) {
      #${BANNER_ID} {
        flex-direction: column;
        text-align: center;
        padding: 12px 16px;
      }
      #${BANNER_ID} button { width: 100%; }
    }
  `;
  parentDoc.head.appendChild(style);

  // ── Banner ─────────────────────────────────────────────────────────────
  const banner = parentDoc.createElement('div');
  banner.id = BANNER_ID;
  banner.innerHTML = `
    <div class="ptar-cookie-text">
      <strong>🍪 Este sitio utiliza cookies</strong>
      Usamos cookies para mantener tu sesión iniciada y recordar las
      preferencias de visualización. No se comparten con terceros ni se
      usan con fines publicitarios.
    </div>
    <button type="button">Entendido</button>
  `;
  parentDoc.body.appendChild(banner);

  banner.querySelector('button').addEventListener('click', () => {
    try { parentStorage.setItem(KEY, 'true'); } catch (e) { /* noop */ }
    banner.remove();
  });
})();
</script>
"""


def render_cookie_banner() -> None:
    """Inyecta (una sola vez por navegador) el aviso de uso de cookies.

    Si el usuario ya hizo click en "Entendido" en una visita previa, el
    `localStorage` evita que vuelva a mostrarse. Llamar idealmente al inicio
    de `home.py`, después de `st.set_page_config` y antes de la auth.
    """
    components_html(_BANNER_SCRIPT, height=0)
