/**
 * Fase 02 — Rutas de Productos.
 * GET    /api/v1/products          — listar (paginado, filtrado)
 * POST   /api/v1/products          — crear
 * GET    /api/v1/products/:id      — detalle
 * PATCH  /api/v1/products/:id      — actualizar
 * DELETE /api/v1/products/:id      — archivar (soft delete)
 * POST   /api/v1/products/:id/publish   — publicar (TENANT_ADMIN / MANAGER)
 * POST   /api/v1/products/:id/unpublish — despublicar
 */

import { FastifyInstance, FastifyRequest } from "fastify";
import { z } from "zod";
import { requireRole } from "../plugins/rbac.js";
import { slugify } from "@fitness-os/shared";

// ── Schemas ────────────────────────────────────────────────────────
const CreateProductSchema = z.object({
  sku: z.string().min(1).max(100),
  name: z.string().min(2).max(500),
  description: z.string().optional(),
  type: z.enum(["PDF_GUIDE", "VIDEO_COURSE", "AUDIO_PROGRAM", "BUNDLE", "SUBSCRIPTION", "COACHING_SESSION", "TEMPLATE", "EBOOK", "CHALLENGE", "COMMUNITY_ACCESS"]),
  categoryId: z.string().min(1).optional(), // cuid2, no UUID
  tags: z.array(z.string()).optional(),
  level: z.string().optional(),         // principiante, intermedio, avanzado
  durationWeeks: z.number().int().optional(),
  objective: z.string().optional(),
  coverImageUrl: z.string().optional(),
  prices: z.array(z.object({
    basePrice: z.number().min(0),
    promoPrice: z.number().min(0).optional(),
    currency: z.enum(["ARS", "UYU", "USD", "MXN", "CLP", "COP", "PEN", "EUR"]).default("ARS"),
    country: z.string().length(2).optional(),
    channel: z.enum(["WEB", "MERCADOLIBRE", "INSTAGRAM", "WHATSAPP"]).default("WEB"),
  })).min(1),
  content: z.object({
    shortDescription: z.string().max(300).optional(),
    longDescription: z.string().optional(),
    benefits: z.array(z.string()).optional(),
    targetAudience: z.string().optional(),
    whatYouGet: z.array(z.string()).optional(),
  }).optional(),
});

const UpdateProductSchema = CreateProductSchema.partial().extend({
  status: z.enum(["DRAFT", "EDITING", "PROFESSIONAL_REVIEW", "APPROVED", "PAUSED", "ARCHIVED"]).optional(),
});

const ListProductsQuerySchema = z.object({
  page: z.string().transform(Number).default("1"),
  pageSize: z.string().transform(Number).default("20"),
  status: z.string().optional(),
  type: z.string().optional(),
  categoryId: z.string().optional(),
  categorySlug: z.string().optional(),
  tag: z.string().optional(), // e.g. "Para Mujeres", "Para Hombres", "Para Todos"
  q: z.string().optional(),
  sortBy: z.enum(["name", "createdAt", "updatedAt", "price"]).default("createdAt"),
  order: z.enum(["asc", "desc"]).default("desc"),
});

// ── Plugin ─────────────────────────────────────────────────────────
export async function productRoutes(fastify: FastifyInstance) {
  const prisma = fastify.prisma;

  /**
   * GET /products — público para PUBLISHED, requiere auth para otros status
   */
  fastify.get("/", {
    preHandler: fastify.authenticateOptional,
  }, async (request: FastifyRequest, reply) => {
    const query = ListProductsQuerySchema.safeParse(request.query);
    if (!query.success) return reply.code(400).send({ error: "Parámetros inválidos" });

    const { page, pageSize, status, type, categoryId, categorySlug, tag, q, sortBy, order } = query.data;

    // Sin auth solo se pueden ver productos PUBLISHED
    const isAuthenticated = !!request.user?.sub;
    const effectiveStatus = !isAuthenticated ? "PUBLISHED" : (status ?? undefined);

    const safePage = Math.max(1, page);
    const safeSize = Math.min(100, Math.max(1, pageSize));
    const skip = (safePage - 1) * safeSize;

    if (!request.tenantId) return reply.code(400).send({ error: "Tenant requerido (X-Tenant-Slug)" });

    // Resolve categorySlug to categoryId if provided
    let resolvedCategoryId = categoryId;
    if (categorySlug && !categoryId) {
      const cat = await prisma.category.findFirst({ where: { tenantId: request.tenantId!, slug: categorySlug } });
      resolvedCategoryId = cat?.id;
    }

    const where = {
      tenantId: request.tenantId!,
      ...(effectiveStatus && { status: effectiveStatus as never }),
      ...(type && { type: type as never }),
      ...(resolvedCategoryId && { categoryId: resolvedCategoryId }),
      ...(tag && { tags: { some: { tag: { name: { equals: tag, mode: "insensitive" as const } } } } }),
      ...(q && {
        OR: [
          { name: { contains: q, mode: "insensitive" as const } },
          { sku: { contains: q, mode: "insensitive" as const } },
          { description: { contains: q, mode: "insensitive" as const } },
        ],
      }),
    };

    const [total, items] = await Promise.all([
      prisma.product.count({ where }),
      prisma.product.findMany({
        where,
        skip,
        take: safeSize,
        orderBy: { [sortBy]: order },
        include: {
          category: { select: { id: true, name: true, slug: true } },
          prices: true,
          tags: { include: { tag: { select: { name: true } } } },
          _count: { select: { files: true, contentPacks: true } },
        },
      }),
    ]);

    return reply.send({
      data: items,
      pagination: {
        page: safePage,
        pageSize: safeSize,
        total,
        totalPages: Math.ceil(total / safeSize),
      },
    });
  });

  /**
   * POST /products
   */
  fastify.post(
    "/",
    { preHandler: [fastify.authenticate, requireRole("CONTENT_MANAGER")] },
    async (request: FastifyRequest, reply) => {
      const body = CreateProductSchema.safeParse(request.body);
      if (!body.success) {
        return reply.code(400).send({ error: "Datos inválidos", details: body.error.flatten() });
      }

      const { sku, name, description, type, categoryId, tags, prices, content, level, durationWeeks, objective, coverImageUrl } = body.data;
      const tenantId = request.tenantId!;

      // Verificar SKU único dentro del tenant
      const existing = await prisma.product.findUnique({ where: { tenantId_sku: { tenantId, sku } } });
      if (existing) return reply.code(409).send({ error: "SKU ya existe en este tenant" });

      const slug = slugify(name);

      const product = await prisma.$transaction(async (tx) => {
        const p = await tx.product.create({
          data: {
            tenantId,
            sku,
            slug,
            name,
            description,
            productType: type as never,
            status: "DRAFT",
            ...(categoryId && { categoryId }),
            ...(level && { level }),
            ...(durationWeeks && { durationWeeks }),
            ...(objective && { objective }),
            ...(coverImageUrl && { coverImageUrl }),
          },
        });

        // Precios
        await tx.productPrice.createMany({
          data: prices.map((price) => ({
            productId: p.id,
            ...price,
          })),
        });

        // Contenido — almacenado como JSON en ProductContent
        if (content) {
          await tx.productContent.create({
            data: {
              productId: p.id,
              channel: "WEB",
              contentType: "description",
              content: JSON.stringify(content),
              status: "DRAFT",
            },
          });
        }

        // Tags
        if (tags?.length) {
          for (const tagName of tags) {
            const tag = await tx.tag.upsert({
              where: { name: tagName },
              update: {},
              create: { name: tagName },
            });
            await tx.productTag.create({ data: { productId: p.id, tagId: tag.id } });
          }
        }

        // Audit
        await tx.auditLog.create({
          data: {
            tenantId,
            userId: request.user.sub,
            action: "PRODUCT_CREATE",
            entity: "Product",
            entityId: p.id,
            after: { sku, name, type },
          },
        });

        return p;
      });

      return reply.code(201).send({ data: product });
    }
  );

  /**
   * GET /products/by-slug/:slug — público, para SEO/tienda
   */
  fastify.get("/by-slug/:slug", {
    preHandler: fastify.authenticateOptional,
  }, async (request: FastifyRequest<{ Params: { slug: string } }>, reply) => {
    if (!request.tenantId) return reply.code(400).send({ error: "Tenant requerido (X-Tenant-Slug)" });

    const product = await prisma.product.findFirst({
      where: {
        slug: request.params.slug,
        tenantId: request.tenantId,
        // Sin auth solo productos publicados
        ...(!request.user?.sub && { status: "PUBLISHED" }),
      },
      include: {
        category: true,
        prices: true,
        files: { select: { id: true, name: true, mimeType: true, sizeBytes: true, createdAt: true } },
        contents: true,
        tags: { include: { tag: true } },
      },
    });

    if (!product) return reply.code(404).send({ error: "Producto no encontrado" });
    return reply.send({ data: product });
  });

  /**
   * GET /products/:id
   */
  fastify.get("/:id", async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
    const product = await prisma.product.findFirst({
      where: { id: request.params.id, tenantId: request.tenantId! },
      include: {
        category: true,
        prices: true,
        files: { select: { id: true, name: true, mimeType: true, sizeBytes: true, createdAt: true } },
        contentPacks: true,
        contents: true,
        tags: { include: { tag: true } },
        versions: { orderBy: { version: "desc" }, take: 5 },
      },
    });

    if (!product) return reply.code(404).send({ error: "Producto no encontrado" });
    return reply.send({ data: product });
  });

  /**
   * PATCH /products/:id
   */
  fastify.patch(
    "/:id",
    { preHandler: [fastify.authenticate, requireRole("CONTENT_MANAGER")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const body = UpdateProductSchema.safeParse(request.body);
      if (!body.success) {
        return reply.code(400).send({ error: "Datos inválidos", details: body.error.flatten() });
      }

      const tenantId = request.tenantId!;
      const product = await prisma.product.findFirst({
        where: { id: request.params.id, tenantId },
      });
      if (!product) return reply.code(404).send({ error: "Producto no encontrado" });

      // No permitir pasar a PUBLISHED desde aquí — usar /publish
      if (body.data.status === "PUBLISHED" as never) {
        return reply.code(400).send({ error: "Use el endpoint /publish para publicar" });
      }

      const { prices, content, tags, ...productData } = body.data;

      const updated = await prisma.$transaction(async (tx) => {
        const p = await tx.product.update({
          where: { id: product.id },
          data: {
            ...productData,
            ...(productData.name && { slug: slugify(productData.name) }),
          },
        });

        if (prices?.length) {
          await tx.productPrice.deleteMany({ where: { productId: p.id } });
          await tx.productPrice.createMany({
            data: prices.map((price) => ({ productId: p.id, ...price })),
          });
        }

        if (content) {
          // ProductContent stores structured content as JSON in the 'content' field
          // We create/update a record with contentType="description" for the product's main content
          const existingContent = await tx.productContent.findFirst({
            where: { productId: p.id, contentType: "description", channel: "WEB" },
          });
          if (existingContent) {
            await tx.productContent.update({
              where: { id: existingContent.id },
              data: { content: JSON.stringify(content), updatedAt: new Date() },
            });
          } else {
            await tx.productContent.create({
              data: {
                productId: p.id,
                channel: "WEB",
                contentType: "description",
                content: JSON.stringify(content),
                status: "DRAFT",
              },
            });
          }
        }

        await tx.auditLog.create({
          data: {
            tenantId,
            userId: request.user.sub,
            action: "PRODUCT_UPDATE",
            entity: "Product",
            entityId: p.id,
            before: { status: product.status },
            after: productData,
          },
        });

        return p;
      });

      return reply.send({ data: updated });
    }
  );

  /**
   * POST /products/:id/publish
   * Solo MANAGER+. Requiere que haya al menos un archivo y un precio.
   */
  fastify.post(
    "/:id/publish",
    { preHandler: [fastify.authenticate, requireRole("MANAGER")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const tenantId = request.tenantId!;
      const product = await prisma.product.findFirst({
        where: { id: request.params.id, tenantId },
        include: {
          files: { take: 1 },
          prices: { take: 1 },
        },
      });

      if (!product) return reply.code(404).send({ error: "Producto no encontrado" });
      if (product.status === "PUBLISHED") return reply.code(409).send({ error: "Ya está publicado" });
      if (product.status === "ARCHIVED") return reply.code(409).send({ error: "No se puede publicar un producto archivado" });
      if (!product.files.length) return reply.code(422).send({ error: "El producto debe tener al menos un archivo antes de publicarse" });
      if (!product.prices.length) return reply.code(422).send({ error: "El producto debe tener al menos un precio antes de publicarse" });

      const published = await prisma.product.update({
        where: { id: product.id },
        data: { status: "PUBLISHED", publishedAt: new Date() },
      });

      await prisma.auditLog.create({
        data: {
          tenantId,
          userId: request.user.sub,
          action: "PRODUCT_PUBLISH",
          entity: "Product",
          entityId: product.id,
        },
      });

      return reply.send({ data: published });
    }
  );

  /**
   * POST /products/:id/unpublish
   */
  fastify.post(
    "/:id/unpublish",
    { preHandler: [fastify.authenticate, requireRole("MANAGER")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const product = await prisma.product.findFirst({
        where: { id: request.params.id, tenantId: request.tenantId! },
      });
      if (!product) return reply.code(404).send({ error: "Producto no encontrado" });

      const updated = await prisma.product.update({
        where: { id: product.id },
        data: { status: "PAUSED" },
      });

      return reply.send({ data: updated });
    }
  );

  /**
   * DELETE /products/:id — Archiva (soft delete)
   */
  fastify.delete(
    "/:id",
    { preHandler: [fastify.authenticate, requireRole("MANAGER")] },
    async (request: FastifyRequest<{ Params: { id: string } }>, reply) => {
      const product = await prisma.product.findFirst({
        where: { id: request.params.id, tenantId: request.tenantId! },
      });
      if (!product) return reply.code(404).send({ error: "Producto no encontrado" });

      await prisma.product.update({
        where: { id: product.id },
        data: { status: "ARCHIVED" },
      });

      return reply.send({ message: "Producto archivado" });
    }
  );
}
