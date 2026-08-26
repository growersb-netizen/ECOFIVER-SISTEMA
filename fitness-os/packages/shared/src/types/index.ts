// ── Tipos compartidos entre apps y packages ──────────────────────

export interface TenantContext {
  tenantId: string;
  userId?: string;
  role?: UserRole;
}

export type UserRole =
  | "SUPER_ADMIN"
  | "TENANT_ADMIN"
  | "MANAGER"
  | "CONTENT_MANAGER"
  | "SALES"
  | "SUPPORT"
  | "COACH"
  | "AFFILIATE"
  | "CUSTOMER";

export type ProductStatus =
  | "DRAFT"
  | "AI_GENERATED"
  | "EDITING"
  | "PROFESSIONAL_REVIEW"
  | "APPROVED"
  | "PUBLISHED"
  | "PAUSED"
  | "ARCHIVED";

export type OrderStatus =
  | "PENDING_PAYMENT"
  | "PAID"
  | "AWAITING_CUSTOMER_DATA"
  | "READY_FOR_FULFILLMENT"
  | "FULFILLMENT_PROCESSING"
  | "DELIVERED"
  | "COMPLETED"
  | "DELIVERY_FAILED"
  | "CANCELLED"
  | "REFUNDED";

export type DeliveryStatus =
  | "PENDING"
  | "AWAITING_CUSTOMER_DATA"
  | "READY"
  | "PROCESSING"
  | "DELIVERED"
  | "FAILED";

export type ChannelType =
  | "WHATSAPP"
  | "INSTAGRAM"
  | "FACEBOOK"
  | "TIKTOK"
  | "YOUTUBE"
  | "EMAIL"
  | "WEB"
  | "MERCADOLIBRE";

export type AutopilotMode = "MANUAL" | "ASSISTED" | "AUTOMATIC";

export type Currency = "ARS" | "UYU" | "USD" | "MXN" | "CLP" | "COP" | "PEN" | "EUR";

export type AIFunction = "GENERATION" | "ATTENTION" | "REASONING" | "ECONOMIC";

// ── API response wrappers ────────────────────────────────────────

export interface ApiSuccess<T> {
  ok: true;
  data: T;
}

export interface ApiError {
  ok: false;
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}

export type ApiResponse<T> = ApiSuccess<T> | ApiError;

// ── Pagination ───────────────────────────────────────────────────

export interface PaginatedResult<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

export interface PaginationParams {
  page?: number;
  pageSize?: number;
}
