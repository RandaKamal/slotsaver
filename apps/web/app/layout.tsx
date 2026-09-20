import type { ReactNode } from "react";
import "./globals.css";

export const metadata = {
  title: "SlotSaver | Dashboard",
  description: "Fewer empty slots. Shorter wait times. Cancellation recovery for appointment-based businesses.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
