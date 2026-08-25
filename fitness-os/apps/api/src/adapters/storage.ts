/**
 * Fase 04 — Adapter de Cloudflare R2 (S3-compatible).
 * Sin costos de egress, ideal para distribución de archivos digitales.
 *
 * Firmado de URLs con TTL configurable (default 15 min = 900s).
 */

import { S3Client, PutObjectCommand, GetObjectCommand, DeleteObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

export interface UploadResult {
  storageKey: string;
  url: string;
  size: number;
  etag?: string;
}

export class R2StorageAdapter {
  private readonly client: S3Client;
  private readonly bucket: string;
  private readonly publicUrl: string;

  constructor() {
    const accountId = process.env["CLOUDFLARE_ACCOUNT_ID"] ?? "";
    const accessKey = process.env["R2_ACCESS_KEY_ID"] ?? "";
    const secretKey = process.env["R2_SECRET_ACCESS_KEY"] ?? "";
    this.bucket = process.env["R2_BUCKET_NAME"] ?? "fitness-os";
    this.publicUrl = process.env["R2_PUBLIC_URL"] ?? "";

    if (!accountId || !accessKey || !secretKey) {
      console.warn("⚠️  R2 credentials no configuradas — storage en modo mock");
    }

    this.client = new S3Client({
      region: "auto",
      endpoint: `https://${accountId}.r2.cloudflarestorage.com`,
      credentials: {
        accessKeyId: accessKey,
        secretAccessKey: secretKey,
      },
    });
  }

  /**
   * Sube un archivo a R2.
   * storageKey: ruta relativa dentro del bucket, ej: "tenants/abc/products/123/guia.pdf"
   */
  async upload(
    storageKey: string,
    data: Buffer | Uint8Array,
    contentType: string,
    metadata?: Record<string, string>
  ): Promise<UploadResult> {
    await this.client.send(
      new PutObjectCommand({
        Bucket: this.bucket,
        Key: storageKey,
        Body: data,
        ContentType: contentType,
        Metadata: metadata,
      })
    );

    return {
      storageKey,
      url: this.publicUrl ? `${this.publicUrl}/${storageKey}` : `r2://${this.bucket}/${storageKey}`,
      size: data.byteLength,
    };
  }

  /**
   * Genera una URL firmada para descarga segura.
   * TTL por defecto: 900 segundos (15 minutos).
   */
  async getSignedDownloadUrl(storageKey: string, ttlSeconds = 900): Promise<string> {
    const command = new GetObjectCommand({
      Bucket: this.bucket,
      Key: storageKey,
    });

    return getSignedUrl(this.client, command, { expiresIn: ttlSeconds });
  }

  /**
   * Elimina un archivo de R2.
   */
  async delete(storageKey: string): Promise<void> {
    await this.client.send(
      new DeleteObjectCommand({
        Bucket: this.bucket,
        Key: storageKey,
      })
    );
  }

  /**
   * Construye una clave de storage para un archivo de producto.
   * Patrón: tenants/{tenantId}/products/{productId}/{filename}
   */
  static buildProductKey(tenantId: string, productId: string, filename: string): string {
    const sanitized = filename.replace(/[^a-zA-Z0-9._-]/g, "_");
    return `tenants/${tenantId}/products/${productId}/${sanitized}`;
  }

  /**
   * Clave para paquetes ZIP con branding.
   * Patrón: tenants/{tenantId}/packages/{packageId}/{filename}
   */
  static buildPackageKey(tenantId: string, packageId: string, filename: string): string {
    return `tenants/${tenantId}/packages/${packageId}/${filename}`;
  }
}
