import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import { TENANT_COOKIE, SITE_COOKIE, getCookieSecurityOptions } from '@/lib/cookie-config';

/**
 * POST /api/switch-site - 切换当前站点
 * 
 * 请求体: { tenant_id: string, site_id: string }
 * 
 * 将 tenant_id 和 site_id 写入 Cookie，后续所有 API 请求
 * 将自动使用这些值作为 Scope。
 */
export async function POST(req: NextRequest) {
  try {
    const { tenant_id, site_id } = await req.json();

    if (!tenant_id || !site_id) {
      return NextResponse.json(
        { error: 'tenant_id and site_id are required' },
        { status: 400 }
      );
    }

    const cookieStore = await cookies();
    const options = getCookieSecurityOptions();
    const maxAge = 60 * 60 * 24 * 30; // 30 天

    // 更新 Scope Cookies
    // 注意：站点切换 Cookie 不需要 httpOnly，因为前端需要读取显示当前站点
    cookieStore.set(TENANT_COOKIE, tenant_id, { 
      ...options, 
      httpOnly: false,
      maxAge,
    });
    cookieStore.set(SITE_COOKIE, site_id, { 
      ...options, 
      httpOnly: false,
      maxAge,
    });

    return NextResponse.json({ 
      success: true,
      tenant_id,
      site_id,
    });
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || 'Failed to switch site' },
      { status: 500 }
    );
  }
}

/**
 * GET /api/switch-site - 获取当前站点信息
 */
export async function GET() {
  const cookieStore = await cookies();
  
  const tenant_id = cookieStore.get(TENANT_COOKIE)?.value || process.env.DEFAULT_TENANT_ID || 'yantian';
  const site_id = cookieStore.get(SITE_COOKIE)?.value || process.env.DEFAULT_SITE_ID || 'yantian-main';

  return NextResponse.json({
    tenant_id,
    site_id,
  });
}
