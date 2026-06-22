import { NextRequest, NextResponse } from 'next/server';
import { manus } from '@/lib/manus';

export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const { skill, params, async: isAsync } = body;

  if (!skill) {
    return NextResponse.json({ error: 'skill name required' }, { status: 400 });
  }

  const result = await manus.executeSkill({
    skill,
    params: params || {},
    async: !!isAsync,
  });

  return NextResponse.json(result);
}
