import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Menu, MessagesSquare, ReceiptText, ScanLine, X } from "lucide-react";

const NAV = [
  { to: "/receipts", label: "Extract", hint: "Receipts & review", icon: ScanLine },
  { to: "/ask", label: "Ask", hint: "Question your spending", icon: MessagesSquare },
];

export default function Layout() {
  const { pathname } = useLocation();
  // Remember which page the mobile drawer was opened on, so navigating closes it.
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn === pathname;

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      {open && (
        <div className="fixed inset-0 z-30 bg-black/40 md:hidden" onClick={() => setOpenOn(null)} />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r border-slate-200 bg-white transition-transform duration-200 md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-16 items-center gap-2 px-5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-900 text-white">
            <ReceiptText size={18} />
          </span>
          <span className="text-lg font-bold text-brand-900">Receipt AI</span>
          <button
            className="ml-auto text-slate-500 md:hidden"
            onClick={() => setOpenOn(null)}
            aria-label="Close menu"
          >
            <X size={20} />
          </button>
        </div>

        <nav className="mt-2 flex-1 space-y-1 px-3">
          {NAV.map(({ to, label, hint, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2.5 transition-colors ${
                  isActive
                    ? "bg-brand-50 text-brand-900"
                    : "text-slate-600 hover:bg-slate-100"
                }`
              }
            >
              <Icon size={20} className="shrink-0" />
              <span className="flex flex-col leading-tight">
                <span className="text-sm font-semibold">{label}</span>
                <span className="text-xs text-slate-400">{hint}</span>
              </span>
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-slate-100 px-5 py-4 text-xs text-slate-400">
          Local models via Ollama
        </div>
      </aside>

      <div className="md:pl-60">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-slate-200 bg-white px-4 md:hidden">
          <button onClick={() => setOpenOn(pathname)} aria-label="Open menu" className="text-slate-600">
            <Menu size={22} />
          </button>
          <span className="font-bold text-brand-900">Receipt AI</span>
        </header>
        <main className="p-4 md:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
