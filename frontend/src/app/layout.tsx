import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ResolveAI - Autonomous Customer Support Agent",
  description: "Next-generation multi-agent IT & customer support resolution portal with LangGraph and Human-in-the-Loop approval workflows.",
};

export default function RootLayout({
  children,
  }: Readonly<{
    children: React.ReactNode;
  }>) {
  return (
    <html lang="en">
      <head>
        <link rel="icon" href="/favicon.ico" sizes="any" />
      </head>
      <body>
        {children}
        <div className="ambient-glow" />
      </body>
    </html>
  );
}
