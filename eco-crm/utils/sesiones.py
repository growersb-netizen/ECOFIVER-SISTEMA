"""
Contrato central de sesiones (JWT) del CRM.

Hay dos clases de sesión firmadas con el mismo SECRET_KEY:
  - CRM    (Usuario):  typ="crm",   aud="ecofiver-crm"
  - Socio  (Aliado):   typ="socio", aud="ecofiver-socios"

Cada consumidor valida SU clase. Antes el CRM no miraba la clase: un token del
panel de socios (sub = id del Aliado) se aceptaba como sesión del Usuario con
ese mismo id —por ejemplo, un administrador—.

Compatibilidad: los tokens emitidos antes de este contrato no tienen "aud".
  - CRM legado: sin "aud" y sin "typ" → se aceptan como CRM (solo los emitía
    create_access_token; duran como máximo 30 días).
  - Socio legado: sin "aud" y typ="socio" → se aceptan solo como socio.
Ningún token se acepta en la otra clase.

Nota: python-jose acepta un token SIN "aud" aunque se le pida audiencia, por eso
la audiencia se comprueba acá de forma explícita.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt

ALGORITHM = "HS256"
AUD_CRM = "ecofiver-crm"
AUD_SOCIO = "ecofiver-socios"
_CLASES = {"crm": AUD_CRM, "socio": AUD_SOCIO}


def emitir(clase: str, sub, secret: str, expira_en: timedelta, extra: Optional[dict] = None) -> str:
    claims = dict(extra or {})
    claims.update({"sub": str(sub), "typ": clase, "aud": _CLASES[clase],
                   "exp": datetime.utcnow() + expira_en})
    return jwt.encode(claims, secret, algorithm=ALGORITHM)


def validar(token: Optional[str], clase: str, secret: str) -> Optional[dict]:
    """Claims si el token es válido, vigente y de esa clase; None en cualquier otro caso."""
    if not token or not secret or clase not in _CLASES:
        return None
    try:
        claims = jwt.get_unverified_claims(token)
        aud = claims.get("aud")
        # Un token con "aud" se valida contra la audiencia de la clase (firma y exp incluidas).
        jwt.decode(token, secret, algorithms=[ALGORITHM],
                   audience=aud if aud is not None else None,
                   options={"require_exp": True, "verify_aud": aud is not None})
    except (JWTError, ValueError, TypeError):
        return None
    typ = claims.get("typ")
    if aud is not None:
        if aud != _CLASES[clase] or typ != clase:
            return None
    else:  # legado
        if clase == "crm" and typ is not None:
            return None
        if clase == "socio" and typ != "socio":
            return None
    try:
        int(claims["sub"])
    except (KeyError, ValueError, TypeError):
        return None
    return claims
