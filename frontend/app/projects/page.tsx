'use client';

import { FormEvent, useEffect, useRef, useState } from 'react';

type Evidence = { value: string; evidence: string[]; confidence: string };
type Project = {
  id: string;
  name: string;
  root_path: string;
  model: {
    languages: Evidence[];
    frameworks: Evidence[];
    package_managers: Evidence[];
    unsupported_languages: Evidence[];
    files_scanned: number;
  };
};
type Plan = { project_id: string; mode: string; tools: { display_name: string; available: boolean; version?: string }[]; tasks: { task_id: string; stage: string; tool: string; target?: string }[] };
type Scan = { id: string; project_id: string; mode: string; status: string; approved: boolean; approval_required: boolean; results: { task_id: string; status: string; output: string }[] };
type RuntimeHealth = { status: string; target?: string; status_code?: number; latency_ms?: number; error?: string };
type GeneratedTest = { id: string; category: string; title: string; method: string; endpoint: string; actor?: string; status: string; expected: Record<string, unknown>; evidence: Record<string, unknown> };
type BehaviorCoverage = { id: string; category: string; title: string; criticality: string; coverage_status: string; source: string };
type ArchitectureMap = { nodes?: { id: string; kind: string; label: string; confidence?: string }[]; edges?: { source: string; target: string; relation: string }[] };
type Report = {
  score: number; grade: string; release_readiness: string; release_blockers: string[]; is_complete_audit: boolean;
  dependency_count: number; api_spec_count: number; api_collection_count: number; api_testing_status: string;
  security_testing_status: string; load_testing_status: string; accessibility_status: string; performance_status: string;
  findings: { title: string; severity: string; status: string; category: string; file_path?: string; line?: string; message: string }[];
  new_findings: number; existing_findings: number; resolved_findings: number;
  generated_test_count: number; generated_test_passed: number; generated_test_failed: number; generated_test_blocked: number;
  generated_tests: GeneratedTest[]; behavior_coverage_total: number; behavior_coverage_covered: number;
  behavior_coverage_partial: number; behavior_coverage_untested: number; behavior_coverage_unknown: number;
  behavior_coverage: BehaviorCoverage[];
  architecture: ArchitectureMap;
};
type ReportHistory = { id: string; scan_id: string; format: string; created_at?: string };
type ManualTest = { id: string; module: string; feature?: string; steps: string[]; expected_result: string; status: string; source: string; accepted: boolean };
type RemediationQueueItem = { finding_title: string; severity?: string; affected_files: string[]; verification_test_count: number; available_actions: string[]; attempt: { id: string; status: string; mode: string; risk: string; finding_confidence: number; fix_confidence: number; impact_radius: Record<string, unknown>; patch?: string } };
type FixPack = { id: string; root_cause_id: string; finding_ids: string[]; correlation_confidence: number; proposed_shared_correction: string; risk: string; status: string };

const API = `${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'}/api`;

export default function ProjectsPage() {
  const [path, setPath] = useState('');
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState<Plan | null>(null);
  const [scan, setScan] = useState<Scan | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [reportHistory, setReportHistory] = useState<ReportHistory[]>([]);
  const [projectScans, setProjectScans] = useState<Scan[]>([]);
  const [runtimePort, setRuntimePort] = useState('');
  const [runtimeHealth, setRuntimeHealth] = useState<RuntimeHealth | null>(null);
  const [aiStatus, setAiStatus] = useState('');
  const [error, setError] = useState('');
  const [scanMode, setScanMode] = useState<'QUICK' | 'STANDARD' | 'FULL'>('STANDARD');
  const [manualTests, setManualTests] = useState<ManualTest[]>([]);
  const [workspaceNotice, setWorkspaceNotice] = useState('');
  const [remediationQueue, setRemediationQueue] = useState<RemediationQueueItem[]>([]);
  const [fixPacks, setFixPacks] = useState<FixPack[]>([]);
  const [previewPatch, setPreviewPatch] = useState('');
  const [activeFindingIndex, setActiveFindingIndex] = useState<number | null>(null);
  const activeFindingRef = useRef<HTMLLIElement | null>(null);
  const pendingFindingFocusRef = useRef(false);

  useEffect(() => {
    if (!pendingFindingFocusRef.current || activeFindingIndex === null) return;
    pendingFindingFocusRef.current = false;
    activeFindingRef.current?.focus();
  }, [activeFindingIndex]);

  useEffect(() => {
    const moveFinding = (event: KeyboardEvent) => {
      if (!report?.findings.length || !event.altKey || !['ArrowDown', 'ArrowUp'].includes(event.key)) return;
      const target = event.target as HTMLElement | null;
      if (target?.matches('input, textarea, select, [contenteditable="true"]')) return;

      event.preventDefault();
      pendingFindingFocusRef.current = true;
      setActiveFindingIndex((current) => {
        const currentIndex = current ?? (event.key === 'ArrowDown' ? -1 : report.findings.length);
        return event.key === 'ArrowDown'
          ? Math.min(currentIndex + 1, report.findings.length - 1)
          : Math.max(currentIndex - 1, 0);
      });
    };

    window.addEventListener('keydown', moveFinding);
    return () => window.removeEventListener('keydown', moveFinding);
  }, [report]);

  function monitorScan(scanId: string, projectId: string) {
    window.localStorage.setItem('qsscope-active-scan', JSON.stringify({ scanId, projectId }));
    const poll = async () => {
      const response = await fetch(`${API}/scans/${scanId}`);
      if (!response.ok) return;
      const status = await response.json() as Scan;
      setScan(status);
      if (['COMPLETED', 'FAILED', 'CANCELLED', 'ERROR'].includes(status.status)) {
        window.clearInterval(timer);
        window.localStorage.removeItem('qsscope-active-scan');
        const reportResponse = await fetch(`${API}/scans/${scanId}/report`);
        if (reportResponse.ok) setReport(await reportResponse.json());
        await loadReportHistory(projectId);
      }
    };
    const timer = window.setInterval(poll, 1000);
    void poll();
    return timer;
  }

  const loadProjects = () => fetch(`${API}/projects`).then(async (response) => {
    if (!response.ok) throw new Error(`Project discovery API returned ${response.status}`);
    const body: unknown = await response.json();
    if (!Array.isArray(body)) throw new Error('Project discovery API returned an invalid response.');
    return body as Project[];
  }).then(setProjects).catch(() => {
    setProjects([]);
    setError('QSScope backend is offline or returned an invalid projects response.');
  });
  useEffect(() => {
    loadProjects();
    fetch(`${API}/settings/ai`).then((res) => res.ok ? res.json() : null).then((body) => {
      if (body) setAiStatus(`${body.provider}: ${body.status}`);
    }).catch(() => undefined);
    const saved = window.localStorage.getItem('qsscope-active-scan');
    if (saved) {
      try {
        const active = JSON.parse(saved) as { scanId: string; projectId: string };
        void showPlan(active.projectId).then(() => monitorScan(active.scanId, active.projectId));
      } catch {
        window.localStorage.removeItem('qsscope-active-scan');
      }
    }
    return () => undefined;
  }, []);

  async function discover(event: FormEvent) {
    event.preventDefault();
    setError('');
    const response = await fetch(`${API}/projects/discover`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ root_path: path }),
    });
    if (!response.ok) {
      const payload = await response.json();
      setError(payload?.error?.message ?? 'Discovery failed.');
      return;
    }
    setPath('');
    await loadProjects();
  }

  async function loadReportHistory(projectId: string) {
    const response = await fetch(`${API}/projects/${projectId}/reports`);
    if (response.ok) setReportHistory(await response.json());
  }

  async function loadProjectScans(projectId: string) {
    const response = await fetch(`${API}/projects/${projectId}/scans`);
    if (response.ok) setProjectScans(await response.json());
  }

  async function openScan(scanId: string) {
    const response = await fetch(`${API}/scans/${scanId}`);
    if (!response.ok) {
      setError('Could not restore the selected scan.');
      return;
    }
    const restored = await response.json() as Scan;
    setScan(restored);
    if (['COMPLETED', 'FAILED', 'CANCELLED', 'ERROR'].includes(restored.status)) {
      const reportResponse = await fetch(`${API}/scans/${scanId}/report`);
      if (reportResponse.ok) setReport(await reportResponse.json());
    } else {
      setReport(null);
      monitorScan(restored.id, restored.project_id);
    }
  }

  async function showPlan(id: string, mode = scanMode) {
    const response = await fetch(`${API}/projects/${id}/scan-plan?mode=${mode}`);
    if (!response.ok) { setError('Could not build scan plan.'); return; }
    setSelected(await response.json());
    await Promise.all([loadReportHistory(id), loadProjectScans(id)]);
    const manual = await fetch(`${API}/projects/${id}/manual-tests`);
    if (manual.ok) setManualTests(await manual.json());
    const [queue, packs] = await Promise.all([
      fetch(`${API}/projects/${id}/remediation-queue`), fetch(`${API}/projects/${id}/fix-packs`),
    ]);
    if (queue.ok) setRemediationQueue(await queue.json());
    if (packs.ok) setFixPacks(await packs.json());
  }

  async function changeMode(mode: 'QUICK' | 'STANDARD' | 'FULL') {
    setScanMode(mode);
    if (selected) await showPlan(selected.project_id, mode);
  }

  async function deriveGeneratedTests() {
    if (!selected) return;
    const response = await fetch(`${API}/projects/${selected.project_id}/generated-tests/derive`, { method: 'POST' });
    const body = await response.json();
    setWorkspaceNotice(response.ok ? `${body.generated} new schema-driven cases; ${body.total} total.` : body?.error?.message ?? 'Could not derive tests.');
  }

  async function deriveManualChecklist() {
    if (!selected) return;
    const response = await fetch(`${API}/projects/${selected.project_id}/manual-tests/derive`, { method: 'POST' });
    if (response.ok) {
      const rows = await response.json();
      setManualTests(rows);
      setWorkspaceNotice(`${rows.length} deterministic manual QA drafts are ready for review.`);
    }
  }

  async function acceptManualTest(id: string) {
    const response = await fetch(`${API}/manual-tests/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ accepted: true }) });
    if (response.ok) setManualTests((current) => current.map((item) => item.id === id ? { ...item, accepted: true } : item));
  }

  async function deriveBehaviorCoverage() {
    if (!selected || !scan) return;
    const response = await fetch(`${API}/projects/${selected.project_id}/behavior-coverage/derive?scan_id=${scan.id}`, { method: 'POST' });
    if (response.ok) {
      const body = await response.json();
      setWorkspaceNotice(`Behavior coverage: ${body.covered} covered, ${body.partially_covered} partial, ${body.untested} untested.`);
      const refreshed = await fetch(`${API}/scans/${scan.id}/report`);
      if (refreshed.ok) setReport(await refreshed.json());
    }
  }

  async function setDisposition(id: string, disposition: 'SKIPPED' | 'MANUAL_REVIEW_REQUIRED') {
    const response = await fetch(`${API}/remediations/${id}/disposition`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ disposition }),
    });
    if (response.ok && selected) await showPlan(selected.project_id, scanMode);
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
    monitorScan(initial.id, selected.project_id);
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
        {aiStatus && <p className="text-xs text-slate-500">AI enrichment: {aiStatus} · deterministic scans remain local</p>}
        <section className="grid gap-4 md:grid-cols-2">
          {projects.map((project) => (
            <article key={project.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <h2 className="text-xl font-semibold">{project.name}</h2>
              <p className="mt-1 truncate text-sm text-slate-500">{project.root_path}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                {[...project.model.languages, ...project.model.frameworks].map((item) => <span key={item.value} className="rounded-full bg-blue-50 px-3 py-1 text-sm text-blue-700 dark:bg-blue-950/40 dark:text-blue-300">{item.value}</span>)}
              </div>
              <p className="mt-4 text-sm text-slate-500">{project.model.files_scanned} files inspected</p>
              {project.model.unsupported_languages.length > 0 && <div className="mt-3 rounded-lg bg-amber-50 p-3 text-xs text-amber-800 dark:bg-amber-950/30 dark:text-amber-200"><b>Partial support:</b> {project.model.unsupported_languages.map((item) => item.value).join(', ')}. Unsupported checks remain explicitly uncovered.</div>}
              <button onClick={() => showPlan(project.id)} className="mt-4 text-sm font-semibold text-blue-600 hover:underline">Build scan plan →</button>
            </article>
          ))}
        </section>
        {selected && <section className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
          <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-xl font-semibold">{selected.mode} scan plan</h2><label className="text-sm">Scan mode <select value={scanMode} onChange={(event) => changeMode(event.target.value as 'QUICK' | 'STANDARD' | 'FULL')} className="ml-2 rounded-lg border border-slate-300 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-950"><option value="QUICK">Quick</option><option value="STANDARD">Standard</option><option value="FULL">Full Audit</option></select></label></div>
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
          <button onClick={deriveGeneratedTests} className="ml-2 mt-5 rounded-lg border border-slate-300 px-4 py-2 font-semibold hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">Derive schema tests</button>
          <button onClick={deriveManualChecklist} className="ml-2 mt-5 rounded-lg border border-slate-300 px-4 py-2 font-semibold hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">Generate manual checklist</button>
          {workspaceNotice && <p className="mt-3 text-sm text-blue-600 dark:text-blue-300">{workspaceNotice}</p>}
        </section>}
        {selected && manualTests.length > 0 && <section className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"><h2 className="text-xl font-semibold">Manual QA workspace</h2><p className="mt-1 text-sm text-slate-500">Generated drafts remain unaccepted until you review them.</p><div className="mt-4 grid gap-3 md:grid-cols-2">{manualTests.map((test) => <article key={test.id} className="rounded-lg border border-slate-200 p-4 dark:border-slate-700"><div className="flex justify-between gap-2"><b>{test.module} · {test.feature}</b><span className="text-xs">{test.status}</span></div><ol className="mt-2 list-decimal pl-5 text-sm text-slate-600 dark:text-slate-300">{test.steps.map((step) => <li key={step}>{step}</li>)}</ol><p className="mt-2 text-xs text-slate-500">Expected: {test.expected_result}</p>{!test.accepted && <button onClick={() => acceptManualTest(test.id)} className="mt-3 text-sm font-semibold text-blue-600 hover:underline">Accept draft</button>}</article>)}</div></section>}
        {selected && (remediationQueue.length > 0 || fixPacks.length > 0) && <section className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"><h2 className="text-xl font-semibold">Remediation queue</h2><p className="mt-1 text-sm text-slate-500">Safe units remain isolated and serialized. There is no unrestricted Fix Everything action.</p><div className="mt-4 space-y-3">{remediationQueue.map((item) => <article key={item.attempt.id} className="rounded-lg border border-slate-200 p-4 dark:border-slate-700"><div className="flex flex-wrap justify-between gap-2"><b>{item.severity} · {item.finding_title}</b><span className="text-sm">{item.attempt.status}</span></div><p className="mt-2 text-xs text-slate-500">{item.attempt.mode} · {item.attempt.risk} risk · finding confidence {Math.round(item.attempt.finding_confidence * 100)}% · fix confidence {Math.round(item.attempt.fix_confidence * 100)}% · {item.verification_test_count} verification checks</p><p className="mt-1 text-xs text-slate-500">Files: {item.affected_files.join(', ') || 'not yet validated'}</p><div className="mt-3 flex flex-wrap gap-3 text-sm font-semibold">{item.available_actions.includes('PREVIEW_FIX') && <button onClick={() => setPreviewPatch(item.attempt.patch ?? 'No patch has been generated yet.')} className="text-blue-600 hover:underline">Preview Fix</button>}{item.available_actions.includes('FIX_VERIFY') && <span className="text-emerald-600">Ready for Fix &amp; Verify API</span>}{item.available_actions.includes('SKIP') && <button onClick={() => setDisposition(item.attempt.id, 'SKIPPED')} className="text-slate-600 hover:underline">Skip</button>}{item.available_actions.includes('MANUAL_REVIEW') && <button onClick={() => setDisposition(item.attempt.id, 'MANUAL_REVIEW_REQUIRED')} className="text-amber-600 hover:underline">Require Manual Review</button>}</div></article>)}</div>{previewPatch && <pre className="mt-4 max-h-80 overflow-auto rounded-lg bg-slate-950 p-4 text-xs text-slate-100">{previewPatch}</pre>}{fixPacks.length > 0 && <><h3 className="mt-7 text-lg font-semibold">Root-cause Fix Packs</h3><div className="mt-3 space-y-2">{fixPacks.map((pack) => <div key={pack.id} className="rounded-lg bg-slate-50 p-4 text-sm dark:bg-slate-800"><b>{pack.root_cause_id}</b> · {pack.risk} · {pack.status}<p className="mt-1">{pack.proposed_shared_correction}</p><p className="mt-1 text-xs text-slate-500">{pack.finding_ids.length} findings · {Math.round(pack.correlation_confidence * 100)}% correlation confidence</p></div>)}</div></>}</section>}
        {reportHistory.length > 0 && <section className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
          <h2 className="text-xl font-semibold">Report export history</h2>
          <ul className="mt-4 space-y-2">{reportHistory.map((item) => <li key={item.id} className="flex justify-between rounded-lg bg-slate-50 p-3 text-sm dark:bg-slate-800"><span>{item.format.toUpperCase()}</span><span className="text-slate-500">{item.created_at ? new Date(item.created_at).toLocaleString() : 'unknown time'}</span></li>)}</ul>
        </section>}
        {selected && projectScans.length > 0 && <section className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
          <h2 className="text-xl font-semibold">Saved scans</h2>
          <p className="mt-1 text-sm text-slate-500">Restore a completed scan to review its evidence, findings, and exports.</p>
          <ul className="mt-4 space-y-2">{projectScans.slice(0, 12).map((item) => <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-slate-50 p-3 text-sm dark:bg-slate-800"><span><b>{item.mode}</b> · {item.status} · {item.id.slice(0, 8)}</span><button onClick={() => openScan(item.id)} className="font-semibold text-blue-600 hover:underline">{scan?.id === item.id ? 'Viewing scan' : 'View scan'}</button></li>)}</ul>
        </section>}
        {scan && <section className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center justify-between"><h2 className="text-xl font-semibold">Scan {scan.status.toLowerCase()}</h2><span className="text-sm text-slate-500">{scan.id.slice(0, 8)}</span></div>
          {scan.status === 'AWAITING_APPROVAL' && <button onClick={approveScan} className="mt-4 rounded-lg bg-amber-600 px-4 py-2 font-semibold text-white hover:bg-amber-700">Approve runtime stages</button>}
          {['AWAITING_APPROVAL', 'PENDING', 'RUNNING'].includes(scan.status) && <button onClick={cancelScan} className="ml-2 mt-4 rounded-lg border border-red-300 px-4 py-2 font-semibold text-red-700 hover:bg-red-50 dark:border-red-900 dark:text-red-300 dark:hover:bg-red-950/30">Cancel scan</button>}
          <ol className="mt-4 space-y-2">{scan.results.map((result) => <li key={result.task_id} className="rounded-lg bg-slate-50 p-3 text-sm dark:bg-slate-800"><b>{result.task_id}</b> · {result.status}</li>)}</ol>
        </section>}
        {report && <section className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center justify-between"><h2 className="text-xl font-semibold">Quality report</h2><span className="text-3xl font-bold text-blue-600">{report.score}/100</span></div>
          <div className={`mt-4 rounded-lg border p-4 ${report.release_readiness === 'NOT READY' ? 'border-red-300 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200' : 'border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-200'}`}>
            <b>{report.release_readiness}</b> · {report.grade} · {report.is_complete_audit ? 'Complete audit' : 'Incomplete audit'}
            {report.release_blockers.length > 0 && <ul className="mt-2 list-disc pl-5 text-sm">{report.release_blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul>}
          </div>
          <p className="mt-2 text-sm text-slate-500">{report.new_findings} new · {report.existing_findings} existing · {report.resolved_findings} resolved findings · {report.dependency_count} dependencies inventoried · {report.api_spec_count} API specs · {report.api_collection_count} Postman collections · API: {report.api_testing_status} · Security: {report.security_testing_status} · Load: {report.load_testing_status} · Accessibility: {report.accessibility_status} · Performance: {report.performance_status}</p>
          <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-lg bg-slate-50 p-4 dark:bg-slate-800"><p className="text-xs uppercase tracking-wide text-slate-500">Generated tests</p><p className="mt-1 text-2xl font-bold">{report.generated_test_count}</p><p className="text-xs text-slate-500">{report.generated_test_passed} passed · {report.generated_test_failed} failed · {report.generated_test_blocked} blocked</p></div>
            <div className="rounded-lg bg-slate-50 p-4 dark:bg-slate-800"><p className="text-xs uppercase tracking-wide text-slate-500">Behaviors covered</p><p className="mt-1 text-2xl font-bold">{report.behavior_coverage_covered}/{report.behavior_coverage_total}</p><p className="text-xs text-slate-500">{report.behavior_coverage_partial} partial · {report.behavior_coverage_untested} untested</p></div>
            <div className="rounded-lg bg-slate-50 p-4 dark:bg-slate-800"><p className="text-xs uppercase tracking-wide text-slate-500">Security findings</p><p className="mt-1 text-2xl font-bold">{report.findings.filter((finding) => finding.category === 'SECURITY').length}</p><p className="text-xs text-slate-500">Deterministic release-gate input</p></div>
            <div className="rounded-lg bg-slate-50 p-4 dark:bg-slate-800"><p className="text-xs uppercase tracking-wide text-slate-500">Execution evidence</p><p className="mt-1 text-2xl font-bold">{scan?.results.length ?? 0}</p><p className="text-xs text-slate-500">Ordered completed task results</p></div>
          </div>
          <button onClick={saveBaseline} className="mt-3 rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">Save baseline</button>
          <button onClick={deriveBehaviorCoverage} className="ml-2 mt-3 rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">Refresh behavior coverage</button>
          <button onClick={() => downloadReport('json')} className="ml-2 mt-3 rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">JSON</button>
          <button onClick={() => downloadReport('markdown')} className="ml-2 mt-3 rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">Markdown</button>
          <button onClick={() => downloadReport('html')} className="ml-2 mt-3 rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">HTML</button>
          <button onClick={() => downloadReport('docx')} className="ml-2 mt-3 rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">DOCX</button>
          <button onClick={() => downloadReport('pdf')} className="ml-2 mt-3 rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">PDF</button>
          {report.findings.length === 0 ? <p className="mt-4 text-sm text-emerald-600">No normalized findings were produced.</p> : <><p className="mt-4 text-sm text-slate-500">Findings explorer · use Alt + ↓ / Alt + ↑ to move between findings.</p><ul className="mt-2 space-y-2" aria-label="Scan findings">{report.findings.map((finding, index) => <li key={`${finding.title}-${index}`} ref={index === activeFindingIndex ? activeFindingRef : undefined} tabIndex={activeFindingIndex === null ? (index === 0 ? 0 : -1) : (index === activeFindingIndex ? 0 : -1)} aria-current={index === activeFindingIndex ? 'true' : undefined} onFocus={() => setActiveFindingIndex(index)} onClick={() => setActiveFindingIndex(index)} className={`rounded-lg border p-3 text-sm outline-none transition-colors motion-reduce:transition-none ${index === activeFindingIndex ? 'border-blue-500 bg-blue-50 ring-2 ring-blue-300 dark:border-blue-400 dark:bg-blue-950/30 dark:ring-blue-700' : 'border-slate-200 focus:border-blue-500 focus:ring-2 focus:ring-blue-300 dark:border-slate-700 dark:focus:border-blue-400 dark:focus:ring-blue-700'}`}><b>{finding.severity}</b> · {finding.status} · {finding.title}<p className="mt-1 text-slate-500">{finding.file_path && `${finding.file_path}:${finding.line ?? ''} — `}{finding.message}</p></li>)}</ul></>}
          <h3 className="mt-7 text-lg font-semibold">Logical Test Matrix</h3>
          {report.generated_tests.filter((test) => test.category === 'LOGICAL').length === 0 ? <p className="mt-2 text-sm text-slate-500">No logical authorization, ownership, or state-transition scenarios were recorded for this scan.</p> : <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-xs uppercase text-slate-500"><tr><th className="p-2">Scenario</th><th className="p-2">Actor</th><th className="p-2">Target</th><th className="p-2">Expected</th><th className="p-2">Status</th></tr></thead><tbody>{report.generated_tests.filter((test) => test.category === 'LOGICAL').map((test) => <tr key={test.id} className="border-t border-slate-200 dark:border-slate-700"><td className="p-2 font-medium">{test.title}</td><td className="p-2">{test.actor ?? 'default'}</td><td className="p-2 font-mono text-xs">{test.method} {test.endpoint}</td><td className="max-w-60 truncate p-2 text-xs">{JSON.stringify(test.expected)}</td><td className="p-2">{test.status}</td></tr>)}</tbody></table></div>}
          <h3 className="mt-7 text-lg font-semibold">Edge Explorer</h3>
          {report.generated_tests.filter((test) => test.category === 'EDGE').length === 0 ? <p className="mt-2 text-sm text-slate-500">No schema-derived boundary scenarios were recorded for this scan.</p> : <div className="mt-3 grid gap-2 sm:grid-cols-2">{report.generated_tests.filter((test) => test.category === 'EDGE').map((test) => <article key={test.id} className="rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-700"><div className="flex justify-between gap-3"><b>{test.title}</b><span>{test.status}</span></div><p className="mt-1 font-mono text-xs text-slate-500">{test.method} {test.endpoint}</p><p className="mt-2 text-xs text-slate-500">Expected: {JSON.stringify(test.expected)}</p></article>)}</div>}
          <h3 className="mt-7 text-lg font-semibold">Security Center</h3>
          {report.findings.filter((finding) => finding.category === 'SECURITY').length === 0 ? <p className="mt-2 text-sm text-emerald-600">No normalized security findings were produced.</p> : <ul className="mt-3 space-y-2">{report.findings.filter((finding) => finding.category === 'SECURITY').map((finding, index) => <li key={`${finding.title}-security-${index}`} className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm dark:border-amber-900 dark:bg-amber-950/20"><b>{finding.severity}</b> · {finding.status} · {finding.title}<p className="mt-1 text-slate-600 dark:text-slate-300">{finding.file_path && `${finding.file_path}:${finding.line ?? ''} — `}{finding.message}</p></li>)}</ul>}
          <h3 className="mt-7 text-lg font-semibold">Tests workspace</h3>
          {report.generated_tests.length === 0 ? <p className="mt-2 text-sm text-slate-500">No generated logical, edge, contract, data, mutation, concurrency, or resilience cases recorded.</p> : <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-xs uppercase text-slate-500"><tr><th className="p-2">Category</th><th className="p-2">Actor</th><th className="p-2">Scenario</th><th className="p-2">Target</th><th className="p-2">Expected</th><th className="p-2">Status</th></tr></thead><tbody>{report.generated_tests.map((test) => <tr key={test.id} className="border-t border-slate-200 dark:border-slate-700"><td className="p-2 font-medium">{test.category}</td><td className="p-2">{test.actor ?? 'default'}</td><td className="p-2">{test.title}</td><td className="p-2 font-mono text-xs">{test.method} {test.endpoint}</td><td className="max-w-60 truncate p-2 text-xs">{JSON.stringify(test.expected)}</td><td className="p-2">{test.status}</td></tr>)}</tbody></table></div>}
          <h3 className="mt-7 text-lg font-semibold">Behavior Coverage &amp; Test Gaps</h3>
          {report.behavior_coverage.length === 0 ? <p className="mt-2 text-sm text-slate-500">Derive behavior coverage after test evidence is available.</p> : <div className="mt-3 grid gap-2 sm:grid-cols-2">{report.behavior_coverage.map((item) => <div key={item.id} className="rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-700"><div className="flex justify-between gap-3"><b>{item.title}</b><span>{item.coverage_status}</span></div><p className="mt-1 text-xs text-slate-500">{item.category} · {item.criticality} criticality · {item.source}</p></div>)}</div>}
          <h3 className="mt-7 text-lg font-semibold">Architecture Map</h3>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{report.architecture.nodes?.map((node) => <div key={node.id} className="rounded-lg border border-slate-200 p-3 dark:border-slate-700"><p className="text-xs font-semibold uppercase tracking-wide text-blue-600">{node.kind}</p><p className="mt-1 font-medium">{node.label}</p>{node.confidence && <p className="mt-1 text-xs text-slate-500">{node.confidence} confidence</p>}</div>)}</div>
          {(report.architecture.edges?.length ?? 0) > 0 && <p className="mt-3 text-xs text-slate-500">{report.architecture.edges?.map((edge) => `${edge.relation}: ${edge.source} → ${edge.target}`).join(' · ')}</p>}
          <h3 className="mt-7 text-lg font-semibold">Evidence Timeline</h3>
          <ol className="mt-3 space-y-2">{scan?.results.map((item, index) => <li key={`${item.task_id}-${index}`} className="flex gap-3 text-sm"><span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-blue-100 text-xs font-bold text-blue-700 dark:bg-blue-950 dark:text-blue-300">{index + 1}</span><span><b>{item.task_id}</b> · {item.status}</span></li>)}</ol>
        </section>}
      </div>
    </main>
  );
}
