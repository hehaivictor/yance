import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "研策 Yance | 专业学位论文开题智能参谋",
  description: "让开题更成体系。证据驱动的专业学位论文开题智能参谋。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
