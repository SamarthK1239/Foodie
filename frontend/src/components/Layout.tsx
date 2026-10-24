import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useInventorySummary } from '../api/hooks'

type NavItem = { to: string; label: string; end?: boolean }

const LINKS: NavItem[] = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/suggestions', label: 'Cook' },
  { to: '/recipes', label: 'Recipes' },
  { to: '/grocery', label: 'Grocery' },
  { to: '/analytics', label: 'Analytics' },
  { to: '/admin', label: 'Admin' },
]

// The four destinations worth one-handed reach on a phone.
const PRIMARY: NavItem[] = [
  { to: '/', label: 'Kitchen', end: true },
  { to: '/suggestions', label: 'Cook' },
  { to: '/grocery', label: 'Grocery' },
  { to: '/analytics', label: 'Stats' },
]

const ICONS: Record<string, string> = {
  '/': 'M3 10.5 12 3l9 7.5V21a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z',
  '/suggestions': 'M12 3a6 6 0 0 0-3 11.2V17a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1v-2.8A6 6 0 0 0 12 3zM10 20h4',
  '/grocery': 'M3 4h2l2.4 11.2a2 2 0 0 0 2 1.6h7.5a2 2 0 0 0 2-1.5L21 8H6M10 21h.01M17 21h.01',
  '/analytics': 'M4 20V10M10 20V4M16 20v-7M22 20H2',
}

function TabIcon({ to }: { to: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-5 w-5"
      aria-hidden="true"
    >
      <path d={ICONS[to]} />
    </svg>
  )
}

export default function Layout() {
  const { data: summary } = useInventorySummary()
  const [menuOpen, setMenuOpen] = useState(false)
  const urgent = summary ? summary.buckets.expired + summary.buckets.critical : 0

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-40 border-b border-white/10 bg-[#0b0f10]/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3 sm:gap-6 sm:px-6">
          <span className="text-lg font-semibold tracking-tight text-emerald-400">Foodie</span>

          <nav className="hidden items-center gap-1 md:flex">
            {LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.end}
                className={({ isActive }) =>
                  `rounded-lg px-3 py-2 text-sm font-medium transition ${
                    isActive ? 'bg-white/10 text-white' : 'text-white/50 hover:text-white'
                  }`
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>

          {urgent > 0 && (
            <span className="ml-auto shrink-0 rounded-full border border-orange-500/30 bg-orange-500/15 px-2.5 py-1 text-xs font-medium text-orange-300">
              {urgent}
              <span className="hidden sm:inline">
                {' '}
                item{urgent === 1 ? ' needs' : 's need'} using
              </span>
            </span>
          )}

          <button
            type="button"
            onClick={() => setMenuOpen((open) => !open)}
            aria-label="Menu"
            aria-expanded={menuOpen}
            className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-white/70 transition hover:bg-white/10 hover:text-white md:hidden ${
              urgent > 0 ? '' : 'ml-auto'
            }`}
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              className="h-5 w-5"
              aria-hidden="true"
            >
              {menuOpen ? <path d="M6 6l12 12M18 6 6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
            </svg>
          </button>
        </div>

        {menuOpen && (
          <nav className="border-t border-white/10 px-4 py-2 md:hidden">
            {LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.end}
                onClick={() => setMenuOpen(false)}
                className={({ isActive }) =>
                  `flex min-h-11 items-center rounded-lg px-3 text-sm font-medium transition ${
                    isActive ? 'bg-white/10 text-white' : 'text-white/60 hover:text-white'
                  }`
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>
        )}
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 pb-28 sm:px-6 sm:py-8 md:pb-8">
        <Outlet />
      </main>

      <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-white/10 bg-[#0b0f10]/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden">
        <div className="flex items-stretch justify-around">
          {PRIMARY.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={({ isActive }) =>
                `flex min-h-14 flex-1 flex-col items-center justify-center gap-1 px-2 py-2 text-[11px] font-medium transition ${
                  isActive ? 'text-emerald-400' : 'text-white/50'
                }`
              }
            >
              <TabIcon to={link.to} />
              {link.label}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  )
}
