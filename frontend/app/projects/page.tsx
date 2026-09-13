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
type Plan = { project_id: string; mode: string; tools: { display_name: string; available: boolean; version?: string }[]; tasks: { task_id: string; stage: string; tool: string; target?: string }[] };
type Scan = { id: string; status: string; approved: boolean; approval_required: boolean; results: { task_id: string; status: string; output: string }[] };
type RuntimeHealth = { status: string; target?: string; status_code?: number; latency_ms?: number; error?: string };
type Report = { score: number; dependency_count: number; api_spec_count: number; api_collection_count: number; api_testing_status: string; security_testing_status: string; load_testing_status: string; accessibility_status: string; performance_status: string; findings: { title: string; severity: string; status: string; file_path?: string; line?: string; message: string }[]; new_findings: number; existing_findings: number; resolved_findings: number };
type ReportHistory = { id: string; scan_id: string; format: string; created_at?: string };

const API = 'http://127.0.0.1:8000/api';

export default function ProjectsPage() {
  const [path, setPath] = useState('');
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState<Plan | null>(null);
  const [scan, setScan] = useState<Scan | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [reportHistory, setReportHistory] = useState<ReportHistory[]>([]);
  const [runtimePort, setRuntimePort] = useState('');
  const [runtimeHealth, setRuntimeHealth] = useState<RuntimeHealth | null>(null);
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

  async function loadReportHistory(projectId: string) {
    const response = await fetch(`${API}/projects/${projectId}/reports`);
    if (response.ok) setReportHistory(await response.json());
  }

  async function showPlan(id: string) {
    const response = await fetch(`${API}/projects/${id}/scan-plan`);
    if (!response.ok) { setError('Could not build scan plan.'); return; }
    setSelected(await response.json());
    await loadReportHistory(id);
  }

  async function startScan() {
    if (!selected) return;
    const response = await fetch(`${API}/projects/${selected.project_id}/scans`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: selected.mode, ...(runtimePort ? { runtime_target: { host: '127.0.0.1', port: Number(runtimePort), scheme: 'http' } } : {}) }),
    });
    if (!response.ok) { setError('Could not start scan.'); return; }
    const initial: Scan = await response.json();
    setScan(initial);
    const timer = window.setInterval(async () => {
      const status = await fetch(`${API}/scans/${initial.id}`).then((res) => res.json()) as Scan;
      setScan(status);
      if (['COMPLETED', 'FAILED', 'CANCELLED', 'ERROR'].includes(status.status)) {
        window.clearInterval(timer);
        fetch(`${API}/scans/${initial.id}/report`).then((res) => res.json()).then(setReport);
        fetch(`${API}/projects/${selected.project_id}/reports`).then((res) => res.json()).then(setReportHistory);
      }

      async function checkRuntimeHealth() {
        if (!selected || !runtimePort) return;
        const configured = await fetch(`${API}/projects/${selected.project_id}/runtime-target`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ host: '127.0.0.1', port: Number(runtimePort), scheme: 'http' }),
        });
        if (!configured.ok) { setError('Could not configure runtime target.'); return; }
        const response = await fetch(`${API}/projects/${selected.project_id}/runtime-target/health`);
        if (response.ok) setRuntimeHealth(await response.json());
        else setError('Could not check runtime target health.');
      }
    }, 1000);
  }

  async function saveBaseline() {
    if (!scan) return;
    const response = await fetch(`${API}/scans/${scan.id}/baseline`, { method: 'POST' });
    if (response.ok) setReport(await response.json());
  }

  async function approveScan() {
    if (!scan) return;
    const response = await fetch(`${API}/scans/${scan.id}/approve`, { method: 'POST' });
    if (response.ok) setScan(await response.json());
  }

  async function cancelScan() {
    if (!scan) return;
    const response = await fetch(`${API}/scans/${scan.id}/cancel`, { method: 'POST' });
    if (response.ok) setScan(await response.json());
  }

  function downloadReport(format: 'json' | 'markdown' | 'html' | 'docx' | 'pdf') {
    if (scan) window.open(`${API}/scans/${scan.id}/report/export?format=${format}`, '_blank', 'noopener,noreferrer');
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
          <ol className="mt-5 space-y-2">{selected.tasks.map((task) => <li key={task.task_id} className="rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-700"><b>{task.stage}</b> · {task.tool}{task.target && ` · ${task.target}`}</li>)}</ol>
          {selected.tasks.some((task) => ['runtime-api', 'runtime-graphql', 'runtime-postman'].includes(task.task_id)) && <label className="mt-5 block text-sm font-medium">Local API port
            <input value={runtimePort} onChange={(event) => setRuntimePort(event.target.value)} type="number" min="1" max="65535" placeholder="8000" className="mt-2 block w-full rounded-lg border border-slate-300 bg-white px-4 py-2 dark:border-slate-700 dark:bg-slate-950" />
            <span className="mt-1 block text-xs text-slate-500">Only 127.0.0.1 is accepted. The API stage remains approval-gated.</span>
            <button type="button" onClick={checkRuntimeHealth} disabled={!runtimePort} className="mt-3 rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800">Check runtime health</button>
            {runtimeHealth && <span className={`ml-3 text-sm ${runtimeHealth.status === 'HEALTHY' ? 'text-emerald-600' : 'text-amber-600'}`}>{runtimeHealth.status}{runtimeHealth.status_code ? ` (${runtimeHealth.status_code})` : ''}{runtimeHealth.latency_ms !== undefined ? ` · ${runtimeHealth.latency_ms} ms` : ''}</span>}
          </label>}
          <button onClick={startScan} className="mt-5 rounded-lg bg-emerald-600 px-4 py-2 font-semibold text-white hover:bg-emerald-700">Run scan</button>
        </section>}
        {reportHistory.length > 0 && <section className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
          <h2 className="text-xl font-semibold">Report export history</h2>
          <ul className="mt-4 space-y-2">{reportHistory.map((item) => <li key={item.id} className="flex justify-between rounded-lg bg-slate-50 p-3 text-sm dark:bg-slate-800"><span>{item.format.toUpperCase()}</span><span className="text-slate-500">{item.created_at ? new Date(item.created_at).toLocaleString() : 'unknown time'}</span></li>)}</ul>
        </section>}
        {scan && <section className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center justify-between"><h2 className="text-xl font-semibold">Scan {scan.status.toLowerCase()}</h2><span className="text-sm text-slate-500">{scan.id.slice(0, 8)}</span></div>
          {scan.status === 'AWAITING_APPROVAL' && <button onClick={approveScan} className="mt-4 rounded-lg bg-amber-600 px-4 py-2 font-semibold text-white hover:bg-amber-700">Approve runtime stages</button>}
          {['AWAITING_APPROVAL', 'PENDING', 'RUNNING'].includes(scan.status) && <button onClick={cancelScan} className="ml-2 mt-4 rounded-lg border border-red-300 px-4 py-2 font-semibold text-red-700 hover:bg-red-50 dark:border-red-900 dark:text-red-300 dark:hover:bg-red-950/30">Cancel scan</button>}
          <ol className="mt-4 space-y-2">{scan.results.map((result) => <li key={result.task_id} className="rounded-lg bg-slate-50 p-3 text-sm dark:bg-slate-800"><b>{result.task_id}</b> · {result.status}</li>)}</ol>
        </section>}
        {report && <section className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center justify-between"><h2 className="text-xl font-semibold">Quality report</h2><span className="text-3xl font-bold text-blue-600">{report.score}/100</span></div>
          <p className="mt-2 text-sm text-slate-500">{report.new_findings} new · {report.existing_findings} existing · {report.resolved_findings} resolved findings · {report.dependency_count} dependencies inventoried · {report.api_spec_count} API specs · {report.api_collection_count} Postman collections · API: {report.api_testing_status} · Security: {report.security_testing_status} · Load: {report.load_testing_status} · Accessibility: {report.accessibility_status} · Performance: {report.performance_status}</p>
          <button onClick={saveBaseline} className="mt-3 rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">Save baseline</button>
          <button onClick={() => downloadReport('json')} className="ml-2 mt-3 rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">JSON</button>
          <button onClick={() => downloadReport('markdown')} className="ml-2 mt-3 rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">Markdown</button>
          <button onClick={() => downloadReport('html')} className="ml-2 mt-3 rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">HTML</button>
          <button onClick={() => downloadReport('docx')} className="ml-2 mt-3 rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">DOCX</button>
          <button onClick={() => downloadReport('pdf')} className="ml-2 mt-3 rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">PDF</button>
          {report.findings.length === 0 ? <p className="mt-4 text-sm text-emerald-600">No normalized findings were produced.</p> : <ul className="mt-4 space-y-2">{report.findings.map((finding, index) => <li key={`${finding.title}-${index}`} className="rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-700"><b>{finding.severity}</b> · {finding.status} · {finding.title}<p className="mt-1 text-slate-500">{finding.file_path && `${finding.file_path}:${finding.line ?? ''} — `}{finding.message}</p></li>)}</ul>}
        </section>}
      </div>
    </main>
  );
}
