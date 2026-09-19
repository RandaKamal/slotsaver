import type { ReactNode } from "react";
import "./globals.css";

export const metadata = {
  title: "Relay",
  description: "AI Recovery Engine for Service Businesses",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
