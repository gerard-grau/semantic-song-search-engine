import type { Metadata } from 'next';
import './globals.css';

import { SiteHeader } from '@/components/site-header';

export const metadata: Metadata = {
  title: 'Semantic Song Search MVP',
  description: 'Stakeholder-facing MVP for a hybrid classic and semantic song search experience.',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <div className="page-shell">
          <SiteHeader />
          <main className="container page-content">{children}</main>
        </div>
      </body>
    </html>
  );
}
