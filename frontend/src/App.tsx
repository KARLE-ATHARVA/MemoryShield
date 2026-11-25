import { useEffect, useState } from 'react'
import {
  ShieldCheck,
  Database,
  Activity,
  GitBranch,
} from 'lucide-react'

type ServiceState = 'checking' | 'connected' | 'unavailable'

export default function App() {
  const [backend, setBackend] = useState<ServiceState>('checking')
  const [database, setDatabase] = useState<ServiceState>('checking')

  useEffect(() => {
    const check = async () => {
      try {
        const health = await fetch('http://127.0.0.1:8000/api/health')
        setBackend(health.ok ? 'connected' : 'unavailable')
      } catch {
        setBackend('unavailable')
      }

      try {
        const ready = await fetch('http://127.0.0.1:8000/api/ready')
        setDatabase(ready.ok ? 'connected' : 'unavailable')
      } catch {
        setDatabase('unavailable')
      }
    }

    void check()
  }, [])

  return (
    <main className="min-h-screen bg-slate-950 text-white">
      <div className="mx-auto max-w-5xl px-6 py-12">
        <header className="flex items-center gap-4">
          <div className="rounded-xl bg-blue-500/15 p-3">
            <ShieldCheck className="h-9 w-9 text-blue-400" />
          </div>
          <div>
            <h1 className="text-3xl font-bold">MemoryShield AI</h1>
            <p className="text-slate-400">
              AI Agent Memory Forensics & Verified Recovery
            </p>
          </div>
        </header>

        <section className="mt-12">
          <p className="text-xs font-semibold uppercase tracking-widest text-blue-400">
            Phase A — Foundation
          </p>
          <h2 className="mt-3 text-2xl font-semibold">
            Development Environment
          </h2>
          <p className="mt-2 text-slate-400">
            Initial system connectivity and engineering setup.
          </p>
        </section>

        <div className="mt-8 grid gap-5 md:grid-cols-3">
          <StatusCard
            icon={<Activity className="text-blue-400" />}
            title="FastAPI Backend"
            status={backend}
          />
          <StatusCard
            icon={<Database className="text-blue-400" />}
            title="PostgreSQL"
            status={database}
          />
          <StatusCard
            icon={<GitBranch className="text-blue-400" />}
            title="Recovery Engine"
            status="Not implemented"
          />
        </div>

        <div className="mt-10 rounded-xl border border-slate-800 bg-slate-900 p-6">
          <h3 className="text-lg font-semibold">Development Roadmap</h3>
          <p className="mt-2 text-slate-400">
            Foundation → Versioned Memory → AI Agent →
            Provenance → Forensics → Selective Recovery →
            Behavioral Verification
          </p>
        </div>

        <footer className="mt-12 text-sm text-slate-500">
          MemoryShield AI · IBM AI Builders Challenge 2026
        </footer>
      </div>
    </main>
  )
}

function StatusCard({
  icon,
  title,
  status,
}: {
  icon: React.ReactNode
  title: string
  status: string
}) {
  const active = status === 'connected'

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <div className="flex items-center gap-3">
        {icon}
        <h3 className="font-medium">{title}</h3>
      </div>
      <p className={
        'mt-5 text-sm font-medium ' +
        (active ? 'text-green-400' : 'text-amber-400')
      }>
        {status}
      </p>
    </div>
  )
}
