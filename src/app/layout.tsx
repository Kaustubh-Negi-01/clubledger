import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Toaster } from "sonner";
import "./globals.css";

const sans = Geist({ subsets: ["latin"], variable: "--font-geist-sans", display: "swap" });
const mono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Skyline Student Association", template: "%s | Skyline" },
  description: "Memberships, tickets, merchandise and the club's money, in one place.",
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
};
export const viewport: Viewport = {
  themeColor: [{ media: "(prefers-color-scheme: light)", color: "#f6f7f9" }, { media: "(prefers-color-scheme: dark)", color: "#0b0d12" }],
};

// Runs before paint so the theme never flashes.
const themeScript = `try{var t=localStorage.getItem('cl-theme');var d=t?t==='dark':matchMedia('(prefers-color-scheme: dark)').matches;document.documentElement.classList.toggle('dark',d)}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="grain min-h-[100dvh] antialiased">
        {children}
        <Toaster position="bottom-right" toastOptions={{ style: { background: "var(--surface)", color: "var(--ink)", border: "1px solid var(--line)", borderRadius: "12px" } }} />
      </body>
    </html>
  );
}
