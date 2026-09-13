import type { Metadata } from 'next';
import { ThemeProvider } from '@/components/theme-provider';
import '@/app/globals.css';

export const metadata: Metadata = {
  title: 'QSScope',
  description: 'Local full-stack quality, security & testing intelligence platform',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="antialiased">
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
