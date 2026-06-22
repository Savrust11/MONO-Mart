import { NextResponse } from 'next/server';
import { manus } from '@/lib/manus';

export const dynamic = 'force-dynamic';

export async function GET() {
  const skills = await manus.listSkills();
  return NextResponse.json({
    skills,
    configured: manus.isConfigured(),
    base_url: process.env.MANUS_API_BASE_URL || 'https://api.manus.space',
  });
}
