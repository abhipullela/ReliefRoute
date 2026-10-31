// app/layout.tsx
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { ToastProvider } from "@/app/components/Toast";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "ReliefRoute — Operator Dashboard",
  description:
    "Autonomous emergency logistics operator dashboard. Monitor AI-generated delivery plans, approve routes, and dispatch drivers in real-time.",
  keywords: ["emergency logistics", "disaster relief", "supply chain", "operator dashboard"],
  robots: "noindex", // Internal tool — do not index
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} dark`}>
      <body className="bg-slate-950 text-slate-100 antialiased font-sans">
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
