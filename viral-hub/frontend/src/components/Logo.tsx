/**
 * Logo Viral Hub — VH con gradiente naranja→rosa→violeta→cian + "VIRAL HUB"
 * Basado en el brand kit oficial.
 */

interface LogoProps {
  /** Muestra solo el isotipo VH sin el texto */
  iconOnly?: boolean;
  /** Tamaño en px del icono (default 32) */
  size?: number;
  className?: string;
}

export function Logo({ iconOnly = false, size = 32, className = "" }: LogoProps) {
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {/* Isotipo VH */}
      <svg
        width={size}
        height={size}
        viewBox="0 0 100 100"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <defs>
          <linearGradient id="vh-grad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%"   stopColor="#FF6800"/>
            <stop offset="33%"  stopColor="#FF2D95"/>
            <stop offset="66%"  stopColor="#7C3AED"/>
            <stop offset="100%" stopColor="#00D4FF"/>
          </linearGradient>
        </defs>
        {/* V */}
        <path
          d="M10 15 L28 70 L46 15"
          stroke="url(#vh-grad)"
          strokeWidth="12"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {/* H vertical left */}
        <path
          d="M54 15 L54 70"
          stroke="url(#vh-grad)"
          strokeWidth="12"
          strokeLinecap="round"
        />
        {/* H crossbar */}
        <path
          d="M54 42 L76 42"
          stroke="url(#vh-grad)"
          strokeWidth="12"
          strokeLinecap="round"
        />
        {/* H vertical right */}
        <path
          d="M76 15 L76 70"
          stroke="url(#vh-grad)"
          strokeWidth="12"
          strokeLinecap="round"
        />
        {/* Speed lines */}
        <line x1="83" y1="61" x2="96" y2="61" stroke="#FF2D95" strokeWidth="5" strokeLinecap="round"/>
        <line x1="83" y1="71" x2="93" y2="71" stroke="#7C3AED" strokeWidth="4" strokeLinecap="round"/>
        <circle cx="97" cy="71" r="4" fill="#00D4FF"/>
      </svg>

      {/* Logotipo texto */}
      {!iconOnly && (
        <span className="font-bold leading-none" style={{ fontFamily: "var(--font-poppins), system-ui" }}>
          <span style={{ color: "#00D4FF" }}>VIRAL</span>
          <span style={{ color: "#FF6800" }}>HUB</span>
        </span>
      )}
    </div>
  );
}
