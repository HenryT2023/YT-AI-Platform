'use client';

import { useState, useEffect } from 'react';
import { ChevronDown, MapPin, Loader2 } from 'lucide-react';

interface Site {
  id: string;
  name: string;
  display_name?: string;
  status: string;
}

interface CurrentScope {
  tenant_id: string;
  site_id: string;
}

export function SiteSwitcher() {
  const [sites, setSites] = useState<Site[]>([]);
  const [currentScope, setCurrentScope] = useState<CurrentScope | null>(null);
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState(false);
  const [isOpen, setIsOpen] = useState(false);

  // 获取站点列表和当前 scope
  useEffect(() => {
    const fetchData = async () => {
      try {
        const [sitesRes, scopeRes] = await Promise.all([
          fetch('/api/admin/sites'),
          fetch('/api/switch-site'),
        ]);

        if (sitesRes.ok) {
          const sitesData = await sitesRes.json();
          setSites(Array.isArray(sitesData) ? sitesData : []);
        }

        if (scopeRes.ok) {
          const scopeData = await scopeRes.json();
          setCurrentScope(scopeData);
        }
      } catch (error) {
        console.error('Failed to fetch sites:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  const handleSwitchSite = async (site: Site) => {
    if (switching || site.id === currentScope?.site_id) {
      setIsOpen(false);
      return;
    }

    setSwitching(true);
    try {
      const res = await fetch('/api/switch-site', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tenant_id: currentScope?.tenant_id || 'yantian',
          site_id: site.id,
        }),
      });

      if (res.ok) {
        // 刷新页面以应用新的 scope
        window.location.reload();
      }
    } catch (error) {
      console.error('Failed to switch site:', error);
    } finally {
      setSwitching(false);
      setIsOpen(false);
    }
  };

  const currentSite = sites.find(s => s.id === currentScope?.site_id);
  const displayName = currentSite?.display_name || currentSite?.name || currentScope?.site_id || '加载中...';

  if (loading) {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 text-sm text-gray-500">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span>加载站点...</span>
      </div>
    );
  }

  // 如果只有一个站点，不显示切换器
  if (sites.length <= 1) {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 text-sm text-gray-600">
        <MapPin className="w-4 h-4" />
        <span>{displayName}</span>
      </div>
    );
  }

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        disabled={switching}
        className="flex items-center gap-2 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
      >
        <MapPin className="w-4 h-4 text-primary-600" />
        <span className="font-medium">{displayName}</span>
        {switching ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <ChevronDown className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
        )}
      </button>

      {isOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-10"
            onClick={() => setIsOpen(false)}
          />

          {/* Dropdown */}
          <div className="absolute left-0 top-full mt-1 w-56 bg-white border rounded-lg shadow-lg z-20">
            <div className="p-2">
              <div className="px-2 py-1 text-xs font-medium text-gray-500 uppercase">
                切换站点
              </div>
              {sites.map((site) => (
                <button
                  key={site.id}
                  onClick={() => handleSwitchSite(site)}
                  className={`w-full flex items-center gap-2 px-2 py-2 text-sm rounded-md transition-colors ${
                    site.id === currentScope?.site_id
                      ? 'bg-primary-50 text-primary-700'
                      : 'text-gray-700 hover:bg-gray-100'
                  }`}
                >
                  <MapPin className="w-4 h-4" />
                  <div className="flex-1 text-left">
                    <div className="font-medium">
                      {site.display_name || site.name}
                    </div>
                    <div className="text-xs text-gray-500">{site.id}</div>
                  </div>
                  {site.id === currentScope?.site_id && (
                    <span className="text-xs bg-primary-100 text-primary-700 px-1.5 py-0.5 rounded">
                      当前
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
