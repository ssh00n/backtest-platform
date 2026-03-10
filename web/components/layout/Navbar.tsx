'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BarChart2, History } from 'lucide-react';

const NAV_LINKS = [
  { href: '/strategy', label: 'Strategy' },
  { href: '/history', label: 'History', icon: History },
  { href: '/paper-trading', label: 'Paper Trading' },
];

const HIDE_NAV_PATHS = ['/login', '/register'];

export function Navbar() {
  const pathname = usePathname();

  if (HIDE_NAV_PATHS.some((p) => pathname.startsWith(p))) return null;

  return (
    <nav className="border-b border-[#1f2937] px-6 py-4 flex items-center justify-between">
      <div className="flex items-center gap-2">
        <BarChart2 className="text-[#26a69a]" size={22} />
        <span className="font-semibold text-lg tracking-tight text-white">WFS Backtest</span>
      </div>
      <div className="flex gap-6 text-sm text-[#9ca3af]">
        {NAV_LINKS.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(href + '/');
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-1 transition-colors ${
                active ? 'text-[#26a69a] font-medium' : 'hover:text-[#f3f4f6]'
              }`}
            >
              {Icon && <Icon size={14} />}
              {label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
