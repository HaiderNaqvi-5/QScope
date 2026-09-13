'use client';

import { FormEvent, useEffect, useState } from 'react';

type Evidence = { value: string; evidence: string[]; confidence: string };
type Project = {
  id: string;
  name: string;
  root_path: string;
  model: {
    languages: Evidence[];
    frameworks: Evidence[];
    package_managers: Evidence[];
    files_scanned: number;
  };
};
type Plan = { mode: string; tools: { display_name: string; available: boolean; version?: string }[]; tasks: { task_id: string; stage: string; tool: string }[] };

const API = 'http://127.0.0.1:8000/api';

export default function ProjectsPage() {
  const [path, setPath] = useState('');
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState<Plan | null>(null);
  const [error, setError] = useState('');

  const loadProjects = () => fetch(`${API}/projects`).then((res) => res.json()).then(setProjects).catch(() => setError('Backend is offline.'));
  useEffect(() => { loadProjects(); }, []);

  async function discover(event: FormEvent) {
    event.preventDefault();
    setError('');
    const response = await fetch(`${API}/projects/discover`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ root_path: path }),
    });
    if (!response.ok) { setError((await response.json()).detail ?? 'Discovery failed.'); return; }
    setPath('');
    await loadProjects();
  }

  async function showPlan(id: string) {
    const response = await fetch(`${API}/projects/${id}/scan-plan`);
    if (!response.ok) { setError('Could not build scan plan.'); return; }
    setSelected(await response.json());
  }

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-12 dark:bg-slate-950">
      <div className="mx-auto max-w-5xl space-y-8">
        <header>
          <p className="text-sm font-semibold uppercase tracking-widest text-blue-600">Project discovery</p>
          <h1 className="mt-2 text-4xl font-bold text-slate-900 dark:text-white">Know what you are scanning.</h1>
          <p className="mt-3 text-slate-600 dark:text-slate-300">QSScope inspects manifests and source extensions locally without executing project code.</p>
        </header>
        <form onSubmit={discover} className="flex gap-3">
          <input value={path} onChange={(event) => setPath(event.target.value)} required placeholder="/path/to/project" className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-4 py-3 dark:border-slate-700 dark:bg-slate-900" />
          <button className="rounded-lg bg-blue-600 px-5 py-3 font-semibold text-white hover:bg-blue-700">Discover</button>
        </form>
        {error && <p className="rounded-lg bg-red-50 p-4 text-red-700 dark:bg-red-950/30 dark:text-red-300">{error}</p>}
        <section className="grid gap-4 md:grid-cols-2">
          {projects.map((project) => (
            <article key={project.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <h2 className="text-xl font-semibold">{project.name}</h2>
              <p className="mt-1 truncate text-sm text-slate-500">{project.root_path}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                {[...project.model.languages, ...project.model.frameworks].map((item) => <span key={item.value} className="rounded-full bg-blue-50 px-3 py-1 text-sm text-blue-700 dark:bg-blue-950/40 dark:text-blue-300">{item.value}</span>)}
              </div>
              <p className="mt-4 text-sm text-slate-500">{project.model.files_scanned} files inspected</p>
              <button onClick={() => showPlan(project.id)} className="mt-4 text-sm font-semibold text-blue-600 hover:underline">Build scan plan →</button>
            </article>
          ))}
        </section>
        {selected && <section className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
          <h2 className="text-xl font-semibold">Standard scan plan</h2>
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {selected.tools.map((tool) => <div key={tool.display_name} className="flex justify-between rounded-lg bg-slate-50 p-3 text-sm dark:bg-slate-800"><span>{tool.display_name}</span><span className={tool.available ? 'text-green-600' : 'text-amber-600'}>{tool.available ? tool.version ?? 'available' : 'missing'}</span></div>)}
          </div>
          <ol className="mt-5 space-y-2">{selected.tasks.map((task) => <li key={task.task_id} className="rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-700"><b>{task.stage}</b> · {task.tool}</li>)}</ol>
        </section>}
      </div>
    </main>
  );
}
