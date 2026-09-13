'use client';

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export default function SettingsPage() {
  const [settings, setSettings] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('http://127.0.0.1:8000/api/settings')
      .then(res => res.json())
      .then(data => {
        setSettings(data);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
  }, []);

  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
      <div className="container mx-auto px-4 py-16">
        <h1 className="text-4xl font-bold mb-8 text-slate-900 dark:text-white">
          Settings
        </h1>

        {loading ? (
          <Card>
            <CardContent className="pt-6">
              <p className="text-muted-foreground">Loading settings...</p>
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardHeader>
              <CardTitle>Application Configuration</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {settings ? (
                  <>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <p className="text-sm text-muted-foreground">Debug Mode</p>
                        <p className="font-medium">{String(settings.debug)}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Log Level</p>
                        <p className="font-medium">{settings.log_level}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">LLM Features</p>
                        <p className="font-medium">{String(settings.enable_llm_features)}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Advanced Testing</p>
                        <p className="font-medium">{String(settings.enable_advanced_testing)}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Host</p>
                        <p className="font-medium">{settings.backend_host}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Port</p>
                        <p className="font-medium">{settings.backend_port}</p>
                      </div>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Data Directory</p>
                      <p className="font-medium break-all text-sm">{settings.data_dir}</p>
                    </div>
                  </>
                ) : (
                  <p className="text-destructive">Failed to load settings</p>
                )}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </main>
  );
}
