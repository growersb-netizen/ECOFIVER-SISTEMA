# Eco Módulos & Piscinas — Sistema Multiagente de Ventas WhatsApp

Sistema de 4 agentes de IA que atienden consultas de WhatsApp como vendedores humanos argentinos.

## Agentes

| Agente | Especialidad | Modalidad |
|--------|-------------|-----------|
| Pablo  | Piscinas    | Contado   |
| Laura  | Piscinas    | Financiación |
| Sabrina| Módulos NCE | Contado   |
| Claudio| Módulos NCE | Financiación |

## Stack

- **Backend**: FastAPI + Python 3.11
- **IA**: Gemini 2.0 Flash (texto + audio nativo)
- **WhatsApp**: Meta Cloud API (webhook)
- **Base de datos**: SQLite con volumen persistente
- **Deploy**: Fly.io (región gru - São Paulo)
- **Dashboard**: Web app mobile-first

---

## Setup local

### 1. Instalar dependencias

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

```bash
cp .env.example .env
# Editá .env con tus tokens
```

### 3. Ejecutar

```bash
python main.py
```

El servidor corre en `http://localhost:8000`
Dashboard en `http://localhost:8000`

---

## Deploy en Fly.io

### Paso 1 — Instalar Fly CLI

```bash
# macOS/Linux
curl -L https://fly.io/install.sh | sh

# Windows (PowerShell)
iwr https://fly.io/install.ps1 -useb | iex
```

### Paso 2 — Login y crear app

```bash
fly auth login
fly apps create ecomodulos-agentes
```

### Paso 3 — Crear volumen persistente (para SQLite)

```bash
fly volumes create ecomodulos_data --region gru --size 1
```

### Paso 4 — Configurar secretos

```bash
fly secrets set GEMINI_API_KEY="AIzaSyAGruN5QxJYxwPVIO5fpV06blU1MVEi3M4"
fly secrets set WHATSAPP_TOKEN="EAABx..."
fly secrets set WHATSAPP_PHONE_NUMBER_ID="123456789012345"
fly secrets set WHATSAPP_VERIFY_TOKEN="ecomodulos_verify_2024"
fly secrets set NOTIFICATION_NUMBER="5491162558279"
```

### Paso 5 — Deploy

```bash
fly deploy
```

### Paso 6 — Ver logs

```bash
fly logs
```

---

## Configurar webhook de WhatsApp

1. Ir a [Meta for Developers](https://developers.facebook.com)
2. Tu App > WhatsApp > Configuración
3. Webhook URL: `https://ecomodulos-agentes.fly.dev/webhook`
4. Verify Token: `ecomodulos_verify_2024`
5. Suscribirse a: `messages`

---

## Estructura de archivos

```
ecomodulos-agentes/
├── main.py              # Servidor FastAPI principal
├── config.py            # Variables de entorno
├── database.py          # SQLite — conversaciones y leads
├── router.py            # Detecta qué agente responde
├── webhook.py           # Recibe mensajes de WhatsApp
├── audio.py             # Procesa audios con Gemini
├── notifications.py     # Envía WhatsApp a Rodo
├── agents/
│   ├── __init__.py
│   ├── base_agent.py    # Clase base con lógica compartida
│   ├── pablo.py         # Piscinas · Contado
│   ├── laura.py         # Piscinas · Financiación
│   ├── sabrina.py       # Módulos · Contado
│   └── claudio.py       # Módulos · Financiación
├── dashboard/
│   ├── index.html       # Dashboard mobile-first
│   ├── styles.css       # Estilos oscuros
│   └── app.js           # Lógica del dashboard
├── Dockerfile
├── fly.toml
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Dashboard

Accesible en la URL raíz del servidor.

- **Resumen**: KPIs del día, agentes activos, últimos leads
- **Leads**: Lista filtrable por score y agente
- **Chats**: Conversaciones con detalle al tap
- **Agentes**: Métricas por agente

---

## Notificaciones automáticas

- **Lead calificado** (tibio/caliente): WhatsApp inmediato a +5491162558279
- **Resumen diario**: Todos los días a las 20:00hs
