-- Migration: Add download fields to Delivery model
-- 2026-08-26

ALTER TABLE "Delivery"
  ADD COLUMN IF NOT EXISTS "downloadUrl" TEXT,
  ADD COLUMN IF NOT EXISTS "downloadExpiresAt" TIMESTAMP(3),
  ADD COLUMN IF NOT EXISTS "downloadToken" TEXT;

-- Unique index on downloadToken (nullable unique)
CREATE UNIQUE INDEX IF NOT EXISTS "Delivery_downloadToken_key" ON "Delivery"("downloadToken");
