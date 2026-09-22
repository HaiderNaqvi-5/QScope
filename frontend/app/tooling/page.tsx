'use client';

import { useCallback, useEffect, useState } from 'react';

type Tool = { id: string; display_name: string; status: string; version?: string; guidance?: string; reason?: string; categories: string[] };
const API = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

export default function ToolingPage() {
  const [tools, setTools] = useState<Tool[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const load = useCallback(async (recheck = false) => {
    setLoading(true); setError('');
    try {
      const response = await fetch(`${API}/api/tooling/${recheck ? 'recheck' : 'status'}`, { method: recheck ? 'POST' : 'GET' });
      if (!response.ok) throw new Error('Tool registry could not be loaded.');
      setTools(await response.json());
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Tool registry could not be loaded.'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  return <div className="mx-auto max-w-6xl px-5 py-10 lg:px-10">
    <header className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.2em] text-blue-500">Local capabilities</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">Tooling preflight</h1><p className="mt-2 max-w-2xl text-sm text-slate-500">Exact availability for analyzers QSScope may invoke. Nothing is installed automatically.</p></div><button onClick={() => void load(true)} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500">Recheck tools</button></header>
    {error && <p role="alert" className="mt-6 rounded-lg border border-red-900/50 bg-red-950/30 p-4 text-sm text-red-300">{error}</p>}
    {loading ? <div className="mt-8 h-40 animate-pulse rounded-xl bg-slate-200 dark:bg-slate-800" /> : <div className="mt-8 overflow-hidden rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-[#0d121b]"><div className="grid grid-cols-[minmax(10rem,1fr)_8rem_minmax(12rem,2fr)] border-b border-slate-200 px-5 py-3 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:border-slate-800"><span>Capability</span><span>Status</span><span>Coverage / action</span></div>{tools.map((tool) => <article key={tool.id} className="grid grid-cols-[minmax(10rem,1fr)_8rem_minmax(12rem,2fr)] gap-3 border-b border-slate-100 px-5 py-4 text-sm last:border-0 dark:border-slate-800/70"><div><p className="font-medium">{tool.display_name}</p><p className="mt-1 font-mono text-xs text-slate-500">{tool.version || tool.id}</p></div><span className={tool.status === 'READY' ? 'text-emerald-500' : 'text-amber-500'}>{tool.status}</span><div className="text-slate-500"><p>{tool.reason}</p>{tool.guidance && <code className="mt-2 block select-all rounded bg-slate-100 px-2 py-1 text-xs dark:bg-slate-900">{tool.guidance}</code>}</div></article>)}</div>}
  </div>;
}
