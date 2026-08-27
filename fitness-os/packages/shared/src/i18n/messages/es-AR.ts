/**
 * Fase 14 — i18n.
 * Mensajes en español rioplatense (es-AR) — idioma principal de la plataforma.
 * Puede extenderse con es-MX, es-CL, pt-BR para expansión regional.
 */
export const messages = {
  app: {
    name: "Fitness Business OS",
    tagline: "Tu negocio fitness, potenciado con IA",
  },

  nav: {
    store: "Tienda",
    categories: "Categorías",
    cart: "Carrito",
    login: "Entrar",
    logout: "Cerrar sesión",
  },

  product: {
    addToCart: "Agregar al carrito",
    buyNow: "Comprar ahora",
    price: "Precio",
    duration: "{weeks} semanas",
    level: {
      principiante: "Principiante",
      intermedio: "Intermedio",
      avanzado: "Avanzado",
    },
    type: {
      DIGITAL: "Digital",
      PHYSICAL: "Físico",
      BUNDLE: "Paquete",
      MEMBERSHIP: "Membresía",
    },
    status: {
      DRAFT: "Borrador",
      AI_GENERATED: "Generado por IA",
      EDITING: "En edición",
      PROFESSIONAL_REVIEW: "En revisión",
      APPROVED: "Aprobado",
      PUBLISHED: "Publicado",
      PAUSED: "Pausado",
      ARCHIVED: "Archivado",
    },
    instantDownload: "Descarga instantánea",
    lifetimeAccess: "Acceso de por vida",
    includes: "¿Qué incluye?",
  },

  checkout: {
    title: "Finalizar compra",
    coupon: "Cupón de descuento",
    couponPlaceholder: "Ingresá tu código",
    applyCoupon: "Aplicar",
    total: "Total",
    pay: "Pagar con MercadoPago",
    processing: "Procesando…",
    securePayment: "Pago seguro",
    instantAccess: "Acceso inmediato",
    allCards: "Todas las tarjetas",
    couponApplied: "Descuento de {pct}% aplicado",
    couponInvalid: "Cupón inválido o expirado",
  },

  order: {
    status: {
      PENDING_PAYMENT: "Pago pendiente",
      PAID: "Pagado",
      AWAITING_CUSTOMER_DATA: "Esperando datos",
      READY_FOR_FULFILLMENT: "Listo para entrega",
      FULFILLMENT_PROCESSING: "Procesando entrega",
      DELIVERED: "Entregado",
      COMPLETED: "Completado",
      DELIVERY_FAILED: "Entrega fallida",
      CANCELLED: "Cancelado",
      REFUNDED: "Reembolsado",
    },
  },

  lead: {
    status: {
      NEW: "Nuevo",
      CONTACTED: "Contactado",
      QUALIFIED: "Calificado",
      PROPOSAL: "Propuesta",
      PURCHASED: "Compró",
      CUSTOMER: "Cliente",
      REPEAT_CUSTOMER: "Cliente recurrente",
      INACTIVE: "Inactivo",
    },
  },

  ai: {
    draft: "BORRADOR",
    draftNote: "Resultado en DRAFT — requiere revisión humana antes de usar",
    generating: "Generando con IA…",
    generate: "✨ Generar borrador",
    copy: "Copiar",
    copied: "✓ Copiado",
    warning: "La IA genera borradores. Siempre revisá antes de publicar.",
    neverPublishes: "La IA nunca publica directamente",
  },

  admin: {
    dashboard: "Dashboard",
    products: "Productos",
    orders: "Órdenes",
    crm: "CRM",
    ai: "IA Generativa",
    social: "Redes Sociales",
    ml: "MercadoLibre",
    coaches: "Coaches",
    affiliates: "Afiliadas",
    blog: "Blog",
    email: "Email",
    config: "Configuración",
    logout: "Cerrar sesión",
  },

  errors: {
    notFound: "No encontramos lo que buscás",
    serverError: "Algo salió mal. Intentá de nuevo.",
    sessionExpired: "Tu sesión expiró. Volvé a ingresar.",
    unauthorized: "No tenés permiso para realizar esta acción.",
    rateLimited: "Demasiadas solicitudes. Esperá un momento.",
  },

  social: {
    platforms: {
      INSTAGRAM: "Instagram",
      FACEBOOK: "Facebook",
      TIKTOK: "TikTok",
      YOUTUBE: "YouTube",
    },
    types: {
      POST: "Publicación",
      STORY: "Historia",
      REEL: "Reel",
      VIDEO: "Video",
      CAROUSEL: "Carrusel",
    },
    draftWarning: "Esta publicación está en DRAFT — no es visible en la plataforma todavía.",
    publishConfirm: "¿Publicar en {platform}? Esta acción es real y pública.",
  },

  dates: {
    locale: "es-AR",
    currency: "ARS",
    timezone: "America/Argentina/Buenos_Aires",
  },
} as const;

export type Messages = typeof messages;
