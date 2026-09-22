'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useTheme } from 'next-themes';
import { Command, Moon, Search, Sun, ScanSearch, Settings, Wrench, FolderKanban } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';

const primary = [
  { href: '/projects', label: 'Projects', icon: FolderKanban },
  { href: '/settings', label: 'Settings', icon: Settings },
  { href: '/tooling', label: 'Tooling', icon: Wrench },
];

const workspace = ['Overview', 'Scan', 'Findings', 'Tests', 'Dependencies', 'Security',
  'Performance', 'Regression', 'Manual QA', 'Reports'];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [query, setQuery] = useState('');
  useEffect(() => setMounted(true), []);
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
      if (event.key === 'Escape') setPaletteOpen(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);
  const commands = [
    ...primary.map((item) => ({ label: `Go to ${item.label}`, keywords: item.label, action: () => router.push(item.href) })),
    { label: 'Toggle color theme', keywords: 'dark light theme appearance', action: () => setTheme(resolvedTheme === 'dark' ? 'light' : 'dark') },
  ].filter((item) => `${item.label} ${item.keywords}`.toLowerCase().includes(query.toLowerCase()));
  const runCommand = (action: () => void) => {
    action();
    setQuery('');
    setPaletteOpen(false);
  };
  return (
    <div className="min-h-screen bg-slate-50 text-slate-950 dark:bg-[#090d14] dark:text-slate-100">
      <a href="#main-content" className="sr-only z-50 rounded-md bg-blue-600 px-4 py-2 text-white focus:not-sr-only focus:fixed focus:left-3 focus:top-3">Skip to content</a>
      <aside className="border-b border-slate-200 bg-white/95 dark:border-slate-800 dark:bg-[#0d121b] md:fixed md:inset-y-0 md:w-64 md:border-b-0 md:border-r">
        <div className="flex h-16 items-center justify-between px-5">
          <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight"><span className="grid h-8 w-8 place-items-center rounded-lg bg-blue-600 text-white"><ScanSearch size={18} /></span>QSScope</Link>
          <div className="flex items-center gap-2">
            <button type="button" aria-label="Open command palette" onClick={() => setPaletteOpen(true)} className="rounded-lg border border-slate-200 p-2 text-slate-500 hover:text-slate-900 dark:border-slate-700 dark:hover:text-white"><Search size={16} /></button>
            <button type="button" aria-label="Toggle color theme" onClick={() => setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')} className="rounded-lg border border-slate-200 p-2 text-slate-500 hover:text-slate-900 dark:border-slate-700 dark:hover:text-white">
              {mounted && resolvedTheme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
            </button>
          </div>
        </div>
        <nav aria-label="Primary navigation" className="flex gap-2 overflow-x-auto px-3 pb-3 md:block md:space-y-1 md:overflow-visible md:pb-0">
          {primary.map(({ href, label, icon: Icon }) => <Link key={href} href={href} className={`flex shrink-0 items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium ${pathname === href ? 'bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300' : 'text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800/70'}`}><Icon size={17} />{label}</Link>)}
        </nav>
        <div className="hidden px-6 pt-7 md:block">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Current project</p>
          <ul className="mt-3 space-y-2 border-l border-slate-800 pl-4 text-sm text-slate-500">
            {workspace.map((label) => <li key={label}>{label}</li>)}
          </ul>
        </div>
        <p className="hidden px-6 pb-5 pt-8 text-xs leading-5 text-slate-500 md:block">Local-first analysis. Project source stays on this machine unless you explicitly invoke AI.</p>
      </aside>
      <main id="main-content" className="min-w-0 md:pl-64">{children}</main>
      {paletteOpen && <div role="presentation" onMouseDown={() => setPaletteOpen(false)} className="fixed inset-0 z-50 grid place-items-start bg-slate-950/45 px-4 pt-[15vh] backdrop-blur-sm">
        <section role="dialog" aria-modal="true" aria-label="Command palette" onMouseDown={(event) => event.stopPropagation()} className="w-full max-w-xl overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900">
          <div className="flex items-center gap-3 border-b border-slate-200 px-4 dark:border-slate-700"><Command size={18} className="text-blue-600" /><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && commands[0]) runCommand(commands[0].action); }} placeholder="Search commands" className="h-14 min-w-0 flex-1 bg-transparent text-sm outline-none" /><kbd className="rounded border border-slate-200 px-1.5 py-0.5 text-xs text-slate-500 dark:border-slate-700">Esc</kbd></div>
          <div className="max-h-72 overflow-y-auto p-2">{commands.length ? commands.map((command) => <button key={command.label} type="button" onClick={() => runCommand(command.action)} className="flex w-full items-center justify-between rounded-lg px-3 py-3 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-800"><span>{command.label}</span><span className="text-xs text-slate-500">Enter</span></button>) : <p className="px-3 py-6 text-sm text-slate-500">No matching commands.</p>}</div>
          <p className="border-t border-slate-200 px-4 py-2 text-xs text-slate-500 dark:border-slate-700"><kbd className="rounded border border-slate-200 px-1 dark:border-slate-700">Ctrl</kbd> / <kbd className="rounded border border-slate-200 px-1 dark:border-slate-700">Cmd</kbd> + K</p>
        </section>
      </div>}
    </div>
  );
}
