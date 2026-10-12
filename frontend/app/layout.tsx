import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: '购物 SHOPPING · AI 电商客服',
  description:
    'AI 客服、客户档案、订单履约与人工售后协作。回答有来源，业务操作可确认。',
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
