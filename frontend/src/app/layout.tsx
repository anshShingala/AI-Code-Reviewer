import type { Metadata } from 'next';
import './globals.css';
import Navbar from '@/components/Navbar';

export const metadata: Metadata = {
  title: 'AI Code Reviewer',
  description: 'Automated AI-driven code reviews on GitHub Pull Requests',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-slate-50 min-h-screen text-slate-900 flex flex-col">
        <Navbar />
        <main className="flex-grow max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {children}
        </main>
        <footer className="border-t border-slate-200 py-6 text-center text-xs text-slate-400 bg-white">
          AI Code Reviewer &copy; {new Date().getFullYear()} — Powered by FastAPI & Google Gemini AI
        </footer>
      </body>
    </html>
  );
}
