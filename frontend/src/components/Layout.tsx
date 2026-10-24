import { NavLink, Outlet } from 'react-router-dom'
import { useInventorySummary } from '../api/hooks'

const LINKS = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/suggestions', label: 'Cook' },
  { to: '/recipes', label: 'Recipes' },
  { to: '/grocery', label: 'Grocery' },
  { to: '/analytics', label: 'Analytics' },
  { to: '/admin', label: 'Admin' },
]

export default function Layout() {
  const { data: summary } = useInventorySummary()
  const urgent = summary ? summary.buckets.expired + summary.buckets.critical : 0

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-40 border-b border-white/10 bg-[#0b0f10]/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-6 px-6 py-3">
          <span className="text-lg font-semibold tracking-tight text-emerald-400">Foodie</span>
          <nav className="flex items-center gap-1">
            {LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.end}
                className={({ isActive }) =>
                  `rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                    isActive ? 'bg-white/10 text-white' : 'text-white/50 hover:text-white'
                  }`
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>
          {urgent > 0 && (
            <span className="ml-auto rounded-full border border-orange-500/30 bg-orange-500/15 px-3 py-1 text-xs font-medium text-orange-300">
              {urgent} item{urgent === 1 ? ' needs' : 's need'} using
            </span>
          )}
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  )
}
