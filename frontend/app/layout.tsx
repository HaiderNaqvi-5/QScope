import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'QSScope — Quality Intelligence Platform',
  description:
    'Local full-stack quality, security & testing intelligence platform',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
