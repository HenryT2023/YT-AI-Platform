import { NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

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
        greeting: '欢迎来到严田！',
      });
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
      greeting: '欢迎来到严田！',
    });
  }
}
