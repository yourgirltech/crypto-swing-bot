import type { Metadata } from "next";
import { IBM_Plex_Sans, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { TickerBar } from "@/components/TickerBar";

const plexSans = IBM_Plex_Sans({
  variable: "--font-plex-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "Swing Bot",
  description: "BTC swing-trading dashboard -- risk-gated, human-approved.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${plexSans.variable} ${jetbrainsMono.variable} h-full`}>
      <body className="flex h-full min-h-screen bg-base text-primary antialiased">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <TickerBar />
          <main className="flex-1 overflow-auto p-4">{children}</main>
        </div>
      </body>
    </html>
  );
}
