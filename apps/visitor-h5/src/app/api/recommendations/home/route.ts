import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

const BACKEND_URL = process.env.NEXT_PUBLIC_LOCAL_OS_MODE === '1'
  ? process.env.YANTIAN_LOCAL_CORE_URL || 'http://127.0.0.1:8793'
  : process.env.BACKEND_URL || 'http://localhost:8000';

export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/api/v1/public/recommendations/home`, {
      headers: {
        'Content-Type': 'application/json',
      },
      cache: 'no-store',
    });

    if (!res.ok) {
      console.error('Backend error:', res.status);
      return NextResponse.json({
        solar_term: {},
        recommended_quests: [],
        achievement_hints: [],
        topics: [],
        greeting: '',
      }, { status: 503 });
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Failed to fetch recommendations:', error);
    return NextResponse.json({
      solar_term: {},
      recommended_quests: [],
      achievement_hints: [],
      topics: [],
      greeting: '',
    }, { status: 503 });
  }
}
