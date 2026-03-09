"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";

export default function RegisterPage() {
  const { register } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await register(email, username, password);
      router.replace("/strategy");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#0f1117] flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-[#f3f4f6] tracking-tight">
            Backtest Platform
          </h1>
          <p className="text-[#9ca3af] text-sm mt-1">Create your account</p>
        </div>

        <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-6 space-y-4">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs text-[#9ca3af] mb-1.5 uppercase tracking-wide">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full bg-[#0f1117] border border-[#1f2937] rounded-lg px-3 py-2.5 text-sm text-[#f3f4f6] focus:outline-none focus:border-[#26a69a] transition-colors"
                placeholder="you@example.com"
              />
            </div>

            <div>
              <label className="block text-xs text-[#9ca3af] mb-1.5 uppercase tracking-wide">
                Username
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                className="w-full bg-[#0f1117] border border-[#1f2937] rounded-lg px-3 py-2.5 text-sm text-[#f3f4f6] focus:outline-none focus:border-[#26a69a] transition-colors"
                placeholder="trader123"
              />
            </div>

            <div>
              <label className="block text-xs text-[#9ca3af] mb-1.5 uppercase tracking-wide">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                className="w-full bg-[#0f1117] border border-[#1f2937] rounded-lg px-3 py-2.5 text-sm text-[#f3f4f6] focus:outline-none focus:border-[#26a69a] transition-colors"
                placeholder="••••••••"
              />
            </div>

            {error && (
              <p className="text-[#ef5350] text-xs">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-[#26a69a] hover:bg-[#2bbbad] disabled:opacity-50 text-white text-sm font-medium py-2.5 rounded-lg transition-colors"
            >
              {loading ? "Creating account..." : "Create Account"}
            </button>
          </form>

          <p className="text-center text-xs text-[#9ca3af]">
            Already have an account?{" "}
            <Link href="/login" className="text-[#26a69a] hover:underline">
              Sign In
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
