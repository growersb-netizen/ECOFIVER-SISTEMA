/**
 * Logo Viral Hub
 * Variantes: horizontal (logo + texto), solo ícono, dark background.
 * Basado en el brand kit oficial.
 */
import Image from "next/image";

interface LogoProps {
  /** Solo muestra el isotipo VH sin texto */
  iconOnly?: boolean;
  /** Variante para fondo oscuro (texto blanco) */
  dark?: boolean;
  /** Altura en px (default: 36) */
  height?: number;
  className?: string;
}

export function Logo({ iconOnly = false, dark = false, height = 36, className = "" }: LogoProps) {
  if (iconOnly) {
    return (
      <Image
        src="/logo-icon.svg"
        alt="Viral Hub"
        height={height}
        width={height}
        priority
        className={className}
      />
    );
  }

  const src = dark ? "/logo-dark.svg" : "/logo.svg";
  // Relación de aspecto del viewBox 280×90 ≈ 3.11
  const width = Math.round(height * 3.11);

  return (
    <Image
      src={src}
      alt="Viral Hub — Tu contenido. Todos tus canales. Un solo clic."
      height={height}
      width={width}
      priority
      className={className}
    />
  );
}

/**
 * Isotipo inline (SVG puro) — útil cuando no se puede usar next/image
 * o cuando se necesita el gradiente directamente (ej: favicon dinámico).
 */
export function LogoIcon({ size = 40, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 80"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      className={className}
    >
      <defs>
        <linearGradient id="lgi-warm" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%"   stopColor="#FFB300"/>
          <stop offset="50%"  stopColor="#FF6800"/>
          <stop offset="100%" stopColor="#FF2D95"/>
        </linearGradient>
        <linearGradient id="lgi-cool" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%"   stopColor="#7C3AED"/>
          <stop offset="100%" stopColor="#00D4FF"/>
        </linearGradient>
      </defs>
      <line x1="8"  y1="8"  x2="28" y2="66" stroke="url(#lgi-warm)" strokeWidth="13" strokeLinecap="round"/>
      <line x1="28" y1="66" x2="48" y2="8"  stroke="url(#lgi-cool)" strokeWidth="13" strokeLinecap="round"/>
      <line x1="48" y1="8"  x2="48" y2="66" stroke="url(#lgi-cool)" strokeWidth="13" strokeLinecap="round"/>
      <line x1="48" y1="37" x2="67" y2="37" stroke="url(#lgi-cool)" strokeWidth="13" strokeLinecap="round"/>
      <line x1="67" y1="8"  x2="67" y2="66" stroke="url(#lgi-cool)" strokeWidth="13" strokeLinecap="round"/>
      <line x1="75" y1="50" x2="88" y2="50" stroke="#FF6800" strokeWidth="5" strokeLinecap="round"/>
      <line x1="75" y1="59" x2="86" y2="59" stroke="#FF2D95" strokeWidth="4" strokeLinecap="round"/>
      <circle cx="92" cy="59" r="4" fill="#7C3AED"/>
    </svg>
  );
}
