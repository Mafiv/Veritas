import type { Metadata } from "next";
import { Space_Grotesk, Source_Sans_3, JetBrains_Mono } from "next/font/google";
import { Toaster } from "sonner";
import "./globals.css";

const display = Space_Grotesk({
  variable: "--font-display",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
});

const body = Source_Sans_3({
  variable: "--font-body",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const mono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "Veritas — Get answers, not approximations",
  description:
    "RAG-based Chat with your data. Upload documents and ask questions with grounded, citation-backed answers.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${display.variable} ${body.variable} ${mono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col font-sans">
        {children}
        <Toaster
          theme="light"
          position="bottom-right"
          toastOptions={{
            className: "font-sans border-line shadow-soft",
          }}
        />
      </body>
    </html>
  );
}
