'use client';

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export default function Home() {
  const [backendStatus, setBackendStatus] = useState<string>('checking...');

  useEffect(() => {
    fetch('http://127.0.0.1:8000/api/health')
      .then(res => {
        if (res.ok) setBackendStatus('online');
        else setBackendStatus('error');
      })
      .catch(() => setBackendStatus('offline'));
  }, []);

  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
      <div className="container mx-auto px-4 py-16">
        <div className="text-center space-y-6 mb-12">
          <h1 className="text-5xl font-bold tracking-tight text-slate-900 dark:text-white">
            QSScope
          </h1>
          <p className="text-xl text-slate-600 dark:text-slate-300">
            Local Full-Stack Quality, Security & Testing Intelligence Platform
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-4xl mx-auto">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Backend Status</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2">
                <div className={`w-3 h-3 rounded-full ${
                  backendStatus === 'online' ? 'bg-green-500' :
                  backendStatus === 'error' ? 'bg-yellow-500' :
                  'bg-red-500'
                }`} />
                <span className="capitalize font-medium">{backendStatus}</span>
              </div>
              <p className="text-sm text-muted-foreground mt-2">
                http://127.0.0.1:8000
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Milestone Status</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 text-sm">
                <p>✓ M0: Bootstrap</p>
                <p>🔄 M1: Foundation</p>
                <p>⏳ M2-M19: Planned</p>
              </div>
            </CardContent>
          </Card>

          <Card className="md:col-span-2">
            <CardHeader>
              <CardTitle className="text-lg">Quick Links</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                <a
                  href="http://127.0.0.1:8000/docs"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block text-blue-600 dark:text-blue-400 hover:underline"
                >
                  → API Documentation
                </a>
                <a
                  href="/settings"
                  className="block text-blue-600 dark:text-blue-400 hover:underline"
                >
                  → Settings
                </a>
                <a
                  href="/projects"
                  className="block text-blue-600 dark:text-blue-400 hover:underline"
                >
                  → Discover a project and build a scan plan
                </a>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </main>
  );
}
