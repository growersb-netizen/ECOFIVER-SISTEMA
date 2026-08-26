"use client";

import { ReactNode } from "react";

interface HoverCardProps {
  children: ReactNode;
  style?: React.CSSProperties;
  hoverBorderColor?: string;
}

export default function HoverCard({ children, style, hoverBorderColor = "#00FF8755" }: HoverCardProps) {
  return (
    <div
      style={{
        background: "#0D0F1A",
        borderRadius: 14,
        border: "1px solid #1A1F35",
        overflow: "hidden",
        transition: "border-color 0.2s, transform 0.2s",
        display: "flex",
        flexDirection: "column",
        cursor: "pointer",
        ...style,
      }}
      onMouseEnter={e => {
        (e.currentTarget as HTMLDivElement).style.borderColor = hoverBorderColor;
        (e.currentTarget as HTMLDivElement).style.transform = "translateY(-2px)";
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLDivElement).style.borderColor = "#1A1F35";
        (e.currentTarget as HTMLDivElement).style.transform = "translateY(0)";
      }}
    >
      {children}
    </div>
  );
}
