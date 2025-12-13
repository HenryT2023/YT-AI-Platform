'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    router.push('/dashboard');
  }, [router]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-center">
        <h1 className="text-2xl font-bold text-primary-700">严田 AI 文明引擎</h1>
        <p className="mt-2 text-gray-600">正在加载...</p>
      </div>
    </div>
  );
}
