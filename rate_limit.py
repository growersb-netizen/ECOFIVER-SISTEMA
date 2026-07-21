"""
Rate limiting centralizado con slowapi.
Importar `limiter` en main.py y en los routers donde se quiera aplicar límites.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
