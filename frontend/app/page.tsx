export default function Home() {
  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100">
      <div className="container mx-auto px-4 py-16">
        <div className="text-center space-y-6">
          <h1 className="text-4xl font-bold tracking-tight text-slate-900">
            QSScope
          </h1>
          <p className="text-xl text-slate-600">
            Local Full-Stack Quality, Security & Testing Intelligence Platform
          </p>
          <p className="text-base text-slate-500">
            Coming soon in Milestone 1: Foundation
          </p>

          <div className="pt-8">
            <div className="inline-block rounded-lg border border-slate-200 bg-white p-8 shadow-sm">
              <h2 className="mb-4 text-lg font-semibold text-slate-900">
                Bootstrap Status
              </h2>
              <ul className="space-y-2 text-left text-sm text-slate-600">
                <li>✓ Repository structure created</li>
                <li>✓ Documentation in place</li>
                <li>✓ Backend scaffolding ready</li>
                <li>✓ Frontend scaffolding ready</li>
                <li>⏳ Milestone 1: Local Foundation (next)</li>
              </ul>
            </div>
          </div>

          <div className="pt-8">
            <a
              href="http://127.0.0.1:8000/docs"
              className="inline-block rounded-lg bg-slate-900 px-6 py-3 font-semibold text-white hover:bg-slate-800 transition-colors"
              target="_blank"
              rel="noopener noreferrer"
            >
              API Documentation
            </a>
          </div>
        </div>
      </div>
    </main>
  );
}
