'use client';

import { useState, useEffect } from 'react';
import { Sun, Calendar, Leaf, BookOpen } from 'lucide-react';

interface SolarTerm {
  id: string;
  code: string;
  name: string;
  order: number;
  month: number;
  day_start: number;
  day_end: number;
  description: string | null;
  farming_advice: string | null;
  cultural_customs: { customs?: string[]; foods?: string[] } | null;
  poems: { title: string; author: string; content: string }[] | null;
}

const seasonColors: Record<number, string> = {
  1: 'bg-blue-100 text-blue-700',    // 冬
  2: 'bg-green-100 text-green-700',  // 春
  3: 'bg-green-100 text-green-700',
  4: 'bg-green-100 text-green-700',
  5: 'bg-red-100 text-red-700',      // 夏
  6: 'bg-red-100 text-red-700',
  7: 'bg-red-100 text-red-700',
  8: 'bg-orange-100 text-orange-700', // 秋
  9: 'bg-orange-100 text-orange-700',
  10: 'bg-orange-100 text-orange-700',
  11: 'bg-blue-100 text-blue-700',   // 冬
  12: 'bg-blue-100 text-blue-700',
};

const seasonNames: Record<number, string> = {
  1: '冬', 2: '春', 3: '春', 4: '春',
  5: '夏', 6: '夏', 7: '夏', 8: '秋',
  9: '秋', 10: '秋', 11: '冬', 12: '冬',
};

export default function SolarTermsPage() {
  const [terms, setTerms] = useState<SolarTerm[]>([]);
  const [currentTerm, setCurrentTerm] = useState<SolarTerm | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedTerm, setSelectedTerm] = useState<SolarTerm | null>(null);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [termsRes, currentRes] = await Promise.all([
        fetch('/api/admin/solar-terms'),
        fetch('/api/admin/solar-terms/current'),
      ]);

      if (termsRes.ok) {
        const data = await termsRes.json();
        setTerms(data);
      }

      if (currentRes.ok) {
        const data = await currentRes.json();
        setCurrentTerm(data);
      }
    } catch (error) {
      console.error('获取节气数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const groupByMonth = (terms: SolarTerm[]) => {
    const groups: Record<number, SolarTerm[]> = {};
    terms.forEach((term) => {
      if (!groups[term.month]) {
        groups[term.month] = [];
      }
      groups[term.month].push(term);
    });
    return groups;
  };

  const monthGroups = groupByMonth(terms);

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">节气农耕</h1>
        <p className="text-gray-600 mt-1">二十四节气与农耕智慧</p>
      </div>

      {/* 当前节气卡片 */}
      {currentTerm && (
        <div className="bg-gradient-to-r from-green-500 to-emerald-600 rounded-xl p-6 mb-6 text-white">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-green-100 text-sm mb-1">当前节气</p>
              <h2 className="text-3xl font-bold mb-2">{currentTerm.name}</h2>
              <p className="text-green-100">
                {currentTerm.month}月{currentTerm.day_start}日 - {currentTerm.day_end}日
              </p>
            </div>
            <Sun className="w-16 h-16 text-green-200" />
          </div>
          {currentTerm.description && (
            <p className="mt-4 text-green-50 text-sm">{currentTerm.description}</p>
          )}
          {currentTerm.farming_advice && (
            <div className="mt-4 bg-white/10 rounded-lg p-3">
              <div className="flex items-center gap-2 mb-1">
                <Leaf className="w-4 h-4" />
                <span className="text-sm font-medium">农耕建议</span>
              </div>
              <p className="text-sm text-green-50">{currentTerm.farming_advice}</p>
            </div>
          )}
        </div>
      )}

      {/* 统计卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">总节气数</p>
              <p className="text-2xl font-bold text-gray-900">{terms.length}</p>
            </div>
            <Calendar className="w-8 h-8 text-green-500" />
          </div>
        </div>
        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">春季节气</p>
              <p className="text-2xl font-bold text-green-600">
                {terms.filter((t) => [2, 3, 4].includes(t.month)).length}
              </p>
            </div>
            <div className="w-8 h-8 bg-green-100 rounded-full flex items-center justify-center text-green-600 font-bold">
              春
            </div>
          </div>
        </div>
        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">夏季节气</p>
              <p className="text-2xl font-bold text-red-600">
                {terms.filter((t) => [5, 6, 7].includes(t.month)).length}
              </p>
            </div>
            <div className="w-8 h-8 bg-red-100 rounded-full flex items-center justify-center text-red-600 font-bold">
              夏
            </div>
          </div>
        </div>
        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">秋冬节气</p>
              <p className="text-2xl font-bold text-orange-600">
                {terms.filter((t) => [8, 9, 10, 11, 12, 1].includes(t.month)).length}
              </p>
            </div>
            <div className="w-8 h-8 bg-orange-100 rounded-full flex items-center justify-center text-orange-600 font-bold">
              秋
            </div>
          </div>
        </div>
      </div>

      {/* 节气列表 */}
      <div className="bg-white rounded-lg border">
        <div className="px-4 py-3 border-b">
          <h3 className="font-semibold text-gray-900">二十四节气</h3>
        </div>

        {loading ? (
          <div className="p-8 text-center text-gray-500">加载中...</div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 p-4">
            {terms.map((term) => (
              <div
                key={term.id}
                onClick={() => setSelectedTerm(term)}
                className={`p-4 rounded-lg border cursor-pointer transition-all hover:shadow-md ${
                  currentTerm?.code === term.code
                    ? 'border-green-500 bg-green-50'
                    : 'border-gray-200 hover:border-gray-300'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span
                    className={`text-xs px-2 py-0.5 rounded ${seasonColors[term.month]}`}
                  >
                    {seasonNames[term.month]}
                  </span>
                  <span className="text-xs text-gray-400">#{term.order}</span>
                </div>
                <h4 className="text-lg font-bold text-gray-900">{term.name}</h4>
                <p className="text-xs text-gray-500 mt-1">
                  {term.month}月{term.day_start}-{term.day_end}日
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 节气详情弹窗 */}
      {selectedTerm && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={() => setSelectedTerm(null)}
        >
          <div
            className="bg-white rounded-xl max-w-lg w-full mx-4 max-h-[80vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <span
                    className={`text-xs px-2 py-0.5 rounded ${seasonColors[selectedTerm.month]}`}
                  >
                    {seasonNames[selectedTerm.month]}季 · 第{selectedTerm.order}个节气
                  </span>
                  <h2 className="text-2xl font-bold text-gray-900 mt-2">
                    {selectedTerm.name}
                  </h2>
                  <p className="text-gray-500">
                    {selectedTerm.month}月{selectedTerm.day_start}日 -{' '}
                    {selectedTerm.day_end}日
                  </p>
                </div>
                <button
                  onClick={() => setSelectedTerm(null)}
                  className="text-gray-400 hover:text-gray-600"
                >
                  ✕
                </button>
              </div>

              {selectedTerm.description && (
                <div className="mb-4">
                  <h3 className="font-semibold text-gray-700 mb-2 flex items-center gap-2">
                    <BookOpen className="w-4 h-4" />
                    节气简介
                  </h3>
                  <p className="text-gray-600 text-sm">{selectedTerm.description}</p>
                </div>
              )}

              {selectedTerm.farming_advice && (
                <div className="mb-4 bg-green-50 rounded-lg p-4">
                  <h3 className="font-semibold text-green-700 mb-2 flex items-center gap-2">
                    <Leaf className="w-4 h-4" />
                    农耕建议
                  </h3>
                  <p className="text-green-600 text-sm">{selectedTerm.farming_advice}</p>
                </div>
              )}

              {selectedTerm.cultural_customs && (
                <div className="mb-4">
                  <h3 className="font-semibold text-gray-700 mb-2">文化习俗</h3>
                  {selectedTerm.cultural_customs.customs && (
                    <div className="flex flex-wrap gap-2 mb-2">
                      {selectedTerm.cultural_customs.customs.map((custom, i) => (
                        <span
                          key={i}
                          className="px-2 py-1 bg-purple-100 text-purple-700 rounded text-xs"
                        >
                          {custom}
                        </span>
                      ))}
                    </div>
                  )}
                  {selectedTerm.cultural_customs.foods && (
                    <div className="flex flex-wrap gap-2">
                      {selectedTerm.cultural_customs.foods.map((food, i) => (
                        <span
                          key={i}
                          className="px-2 py-1 bg-orange-100 text-orange-700 rounded text-xs"
                        >
                          🍽️ {food}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {selectedTerm.poems && selectedTerm.poems.length > 0 && (
                <div className="bg-gray-50 rounded-lg p-4">
                  <h3 className="font-semibold text-gray-700 mb-2">相关诗词</h3>
                  {selectedTerm.poems.map((poem, i) => (
                    <div key={i} className="text-sm">
                      <p className="text-gray-800 italic">"{poem.content}"</p>
                      <p className="text-gray-500 text-xs mt-1">
                        —— {poem.author}《{poem.title}》
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
