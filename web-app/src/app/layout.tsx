import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import { ClerkProvider, Show, UserButton } from "@clerk/nextjs";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AI Voicemail",
  description: "An AI secretary that answers missed calls and sends useful recaps.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full bg-[#f6f7f3] text-[#111827]">
        <ClerkProvider>
          <header className="border-b border-[#d9dfd3] bg-white/90">
            <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-5">
              <Link className="text-sm font-semibold text-[#111827]" href="/">
                AI VOICEMAIL
              </Link>
              <nav className="flex items-center gap-2">
                <Show when="signed-out">
                  <Link
                    className="flex h-9 items-center rounded-md border border-[#cfd7cb] px-3 text-sm font-medium text-[#273244] transition hover:bg-[#edf2ea]"
                    href="/sign-in"
                  >
                    Sign in
                  </Link>
                  <Link
                    className="flex h-9 items-center rounded-md bg-[#0f5132] px-3 text-sm font-medium text-white transition hover:bg-[#0b3d26]"
                    href="/sign-in"
                  >
                    Sign up
                  </Link>
                </Show>
                <Show when="signed-in">
                  <UserButton />
                </Show>
              </nav>
            </div>
          </header>
          {children}
        </ClerkProvider>
      </body>
    </html>
  );
}
