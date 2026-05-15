"""Autenticación compartida entre dashboards.

`setup_auth()` es idempotente: lo puede llamar tanto el orquestador `home.py`
como cada dashboard individual. Si la cookie de sesión es válida, no muestra
form de login; si no, lo muestra y hace `st.stop()` hasta que el usuario
ingrese credenciales correctas.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st
import streamlit_authenticator as stauth
import yaml

_ROOT = Path(__file__).resolve().parent.parent
_CREDS_FILE = _ROOT / "credentials.yaml"


_AUTH_CACHE_KEY = "_pt_authenticator"


def setup_auth() -> stauth.Authenticate:
    """Garantiza que el usuario esté autenticado. Devuelve el authenticator.

    Idempotente: si el usuario ya está autenticado en esta sesión (cookie
    válida + session_state poblado), devuelve el authenticator cacheado SIN
    volver a invocar `auth.login()`. Eso evita duplicar widgets internos
    (`StreamlitDuplicateElementKey`) cuando este helper se llama tanto desde
    `home.py` como desde un dashboard.

    Casos:
    - `credentials.yaml` no existe → error y stop.
    - Ya autenticado → retorna authenticator cacheado, no toca nada más.
    - Cookie válida pero no en session_state → instancia auth, llama login()
      una sola vez, cachea el authenticator.
    - Sin auth → muestra form, st.stop() hasta que el usuario complete.
    """
    # Atajo idempotente: si ya estamos autenticados Y tenemos el authenticator
    # cacheado, NO crear otro ni llamar login() de nuevo.
    if st.session_state.get("authentication_status") is True:
        cached = st.session_state.get(_AUTH_CACHE_KEY)
        if cached is not None:
            return cached

    if not _CREDS_FILE.exists():
        st.error("No se encontró `credentials.yaml`. Contacta al administrador.")
        st.stop()

    with open(_CREDS_FILE, encoding="utf-8") as f:
        creds_cfg = yaml.safe_load(f)

    auth = stauth.Authenticate(
        str(_CREDS_FILE.resolve()),
        creds_cfg["cookie"]["name"],
        creds_cfg["cookie"]["key"],
        creds_cfg["cookie"]["expiry_days"],
    )

    # Solo llamamos login() la primera vez. Si ya hay auth_status=True pero
    # no había cache (e.g. caso raro de rerun cruzado), evitamos duplicar el
    # widget de login.
    if st.session_state.get("authentication_status") is not True:
        auth.login(location="main")

    if st.session_state.get("authentication_status") is False:
        st.error("Usuario o contraseña incorrectos.")
        st.stop()
    elif st.session_state.get("authentication_status") is None:
        st.stop()

    st.session_state[_AUTH_CACHE_KEY] = auth
    return auth
