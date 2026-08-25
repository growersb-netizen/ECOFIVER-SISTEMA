/**
 * Adapter R2 para el fulfillment worker.
 * Reutiliza la lógica del API adapter.
 */

import { S3Client, GetObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

export class R2StorageAdapter {
  private readonly client: S3Client;
  private readonly bucket: string;

  constructor() {
    const accountId = process.env["CLOUDFLARE_ACCOUNT_ID"] ?? "";
    this.bucket = process.env["R2_BUCKET_NAME"] ?? "fitness-os";

    this.client = new S3Client({
      region: "auto",
      endpoint: `https://${accountId}.r2.cloudflarestorage.com`,
      credentials: {
        accessKeyId: process.env["R2_ACCESS_KEY_ID"] ?? "",
        secretAccessKey: process.env["R2_SECRET_ACCESS_KEY"] ?? "",
      },
    });
  }

  async getSignedDownloadUrl(storageKey: string, ttlSeconds = 900): Promise<string> {
    if (!process.env["CLOUDFLARE_ACCOUNT_ID"]) {
      return `https://mock-r2.example.com/${storageKey}?token=mock&ttl=${ttlSeconds}`;
    }

    return getSignedUrl(
      this.client,
      new GetObjectCommand({ Bucket: this.bucket, Key: storageKey }),
      { expiresIn: ttlSeconds }
    );
  }
}
