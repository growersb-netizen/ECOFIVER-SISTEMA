"""Política: el CRM usa solo OpenRouter para IA."""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import ai_client


def test_solo_openrouter_en_la_prioridad():
    assert ai_client.PROVIDER_PRIORITY == ["openrouter"]


def test_con_solo_clave_de_gemini_no_usa_ia():
    claves = {"gemini_api_key": "AIza" + "x" * 30, "grok_api_key": "xai-" + "x" * 30}
    with patch.object(ai_client, "get_config_value", side_effect=lambda c, db: claves.get(c)):
        assert ai_client.get_active_provider(None) == (None, None)


def test_con_clave_openrouter_usa_openrouter():
    claves = {"openrouter_api_key": "sk-or-" + "x" * 30, "gemini_api_key": "AIza" + "x" * 30}
    with patch.object(ai_client, "get_config_value", side_effect=lambda c, db: claves.get(c)):
        assert ai_client.get_active_provider(None)[0] == "openrouter"


def test_ecopost_e_imagenes_sin_llamadas_directas():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for f in ("routers/ecopost.py", "routers/imagenes.py"):
        src = open(os.path.join(base, f), encoding="utf-8").read()
        assert "generativelanguage.googleapis.com" not in src
        assert "huggingface.co" not in src
