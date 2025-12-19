'use client';

import { useState, useEffect } from 'react';
import { Plus, Trash2, Edit2, BookOpen, Leaf, X } from 'lucide-react';

interface FarmingKnowledge {
  id: string;
  solar_term_code: string | null;
  category: string;
  title: string;
  content: string;
  media_urls: { images?: string[] } | null;
  is_active: boolean;
  sort_order: number;
  created_at: string;
}

interface SolarTerm {
  code: string;
  name: string;
}

const categoryLabels: Record<string, { label: string; color: string }> = {
  crop: { label: '作物种植', color: 'bg-green-100 text-green-700' },
  tool: { label: '农具使用', color: 'bg-blue-100 text-blue-700' },
  technique: { label: '农耕技术', color: 'bg-purple-100 text-purple-700' },
  custom: { label: '民俗文化', color: 'bg-orange-100 text-orange-700' },
  general: { label: '通用知识', color: 'bg-gray-100 text-gray-700' },
};

export default function FarmingKnowledgePage() {
  const [items, setItems] = useState<FarmingKnowledge[]>([]);
  const [solarTerms, setSolarTerms] = useState<SolarTerm[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);

  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    solar_term_code: '',
    category: 'general',
    title: '',
    content: '',
    is_active: true,
    sort_order: 0,
  });

  const [filterTerm, setFilterTerm] = useState('');
  const [filterCategory, setFilterCategory] = useState('');

  useEffect(() => {
    fetchSolarTerms();
    fetchItems();
  }, [filterTerm, filterCategory]);

  const fetchSolarTerms = async () => {
    try {
      const res = await fetch('/api/admin/solar-terms');
      if (res.ok) {
        const data = await res.json();
        setSolarTerms(data.map((t: any) => ({ code: t.code, name: t.name })));
      }
    } catch (error) {
      console.error('获取节气列表失败:', error);
    }
  };

  const fetchItems = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterTerm) params.append('solar_term_code', filterTerm);
      if (filterCategory) params.append('category', filterCategory);

      const res = await fetch(`/api/admin/farming-knowledge?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setItems(data.items || []);
        setTotal(data.total || 0);
      }
    } catch (error) {
      console.error('获取农耕知识失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async () => {
    if (!formData.title || !formData.content) {
      alert('请填写标题和内容');
      return;
    }

    try {
      const url = editingId
        ? `/api/admin/farming-knowledge/${editingId}`
        : '/api/admin/farming-knowledge';
      const method = editingId ? 'PATCH' : 'POST';

      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...formData,
          solar_term_code: formData.solar_term_code || null,
        }),
      });

      if (res.ok) {
        setShowForm(false);
        setEditingId(null);
        resetForm();
        fetchItems();
      } else {
        const error = await res.json();
        alert(error.detail || '操作失败');
      }
    } catch (error) {
      console.error('保存失败:', error);
      alert('保存失败');
    }
  };

  const handleEdit = (item: FarmingKnowledge) => {
    setFormData({
      solar_term_code: item.solar_term_code || '',
      category: item.category,
      title: item.title,
      content: item.content,
      is_active: item.is_active,
      sort_order: item.sort_order,
    });
    setEditingId(item.id);
    setShowForm(true);
  };

  const handleDelete = async (id: string, title: string) => {
    if (!confirm(`确定要删除「${title}」吗？`)) return;

    try {
      const res = await fetch(`/api/admin/farming-knowledge/${id}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        fetchItems();
      } else {
        alert('删除失败');
      }
    } catch (error) {
      console.error('删除失败:', error);
    }
  };

  const resetForm = () => {
    setFormData({
      solar_term_code: '',
      category: 'general',
      title: '',
      content: '',
      is_active: true,
      sort_order: 0,
    });
  };

  const getTermName = (code: string | null) => {
    if (!code) return '-';
    const term = solarTerms.find((t) => t.code === code);
    return term?.name || code;
  };

  return (
    <div className="p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">农耕知识管理</h1>
          <p className="text-gray-600 mt-1">管理与节气相关的农耕知识内容</p>
        </div>
        <button
          onClick={() => {
            resetForm();
            setEditingId(null);
            setShowForm(true);
          }}
          className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
        >
          <Plus className="w-5 h-5" />
          添加知识
        </button>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">知识总数</p>
              <p className="text-2xl font-bold text-gray-900">{total}</p>
            </div>
            <BookOpen className="w-8 h-8 text-green-500" />
          </div>
        </div>
        {Object.entries(categoryLabels).slice(0, 3).map(([key, { label, color }]) => (
          <div key={key} className="bg-white rounded-lg border p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">{label}</p>
                <p className="text-2xl font-bold text-gray-900">
                  {items.filter((i) => i.category === key).length}
                </p>
              </div>
              <span className={`px-2 py-1 rounded text-xs ${color}`}>{label}</span>
            </div>
          </div>
        ))}
      </div>

      {/* 筛选器 */}
      <div className="bg-white rounded-lg border p-4 mb-6">
        <div className="flex gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">按节气筛选</label>
            <select
              value={filterTerm}
              onChange={(e) => setFilterTerm(e.target.value)}
              className="border rounded-lg px-3 py-2 min-w-[150px]"
            >
              <option value="">全部节气</option>
              {solarTerms.map((term) => (
                <option key={term.code} value={term.code}>
                  {term.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">按分类筛选</label>
            <select
              value={filterCategory}
              onChange={(e) => setFilterCategory(e.target.value)}
              className="border rounded-lg px-3 py-2 min-w-[150px]"
            >
              <option value="">全部分类</option>
              {Object.entries(categoryLabels).map(([key, { label }]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* 创建/编辑表单 */}
      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-bold">
                  {editingId ? '编辑农耕知识' : '添加农耕知识'}
                </h2>
                <button
                  onClick={() => setShowForm(false)}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      关联节气
                    </label>
                    <select
                      value={formData.solar_term_code}
                      onChange={(e) =>
                        setFormData({ ...formData, solar_term_code: e.target.value })
                      }
                      className="w-full border rounded-lg px-3 py-2"
                    >
                      <option value="">不关联节气</option>
                      {solarTerms.map((term) => (
                        <option key={term.code} value={term.code}>
                          {term.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      分类 *
                    </label>
                    <select
                      value={formData.category}
                      onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                      className="w-full border rounded-lg px-3 py-2"
                    >
                      {Object.entries(categoryLabels).map(([key, { label }]) => (
                        <option key={key} value={key}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    标题 *
                  </label>
                  <input
                    type="text"
                    value={formData.title}
                    onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                    placeholder="例如：春分时节水稻育秧技术"
                    className="w-full border rounded-lg px-3 py-2"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    内容 *
                  </label>
                  <textarea
                    value={formData.content}
                    onChange={(e) => setFormData({ ...formData, content: e.target.value })}
                    placeholder="详细描述农耕知识内容..."
                    rows={6}
                    className="w-full border rounded-lg px-3 py-2"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      排序
                    </label>
                    <input
                      type="number"
                      value={formData.sort_order}
                      onChange={(e) =>
                        setFormData({ ...formData, sort_order: parseInt(e.target.value) || 0 })
                      }
                      className="w-full border rounded-lg px-3 py-2"
                    />
                  </div>
                  <div className="flex items-center">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={formData.is_active}
                        onChange={(e) =>
                          setFormData({ ...formData, is_active: e.target.checked })
                        }
                        className="w-4 h-4"
                      />
                      <span className="text-sm text-gray-700">启用</span>
                    </label>
                  </div>
                </div>
              </div>

              <div className="mt-6 flex gap-2">
                <button
                  onClick={handleSubmit}
                  className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
                >
                  {editingId ? '保存修改' : '创建'}
                </button>
                <button
                  onClick={() => setShowForm(false)}
                  className="px-4 py-2 border rounded-lg hover:bg-gray-50"
                >
                  取消
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 知识列表 */}
      <div className="bg-white rounded-lg border">
        {loading ? (
          <div className="p-8 text-center text-gray-500">加载中...</div>
        ) : items.length === 0 ? (
          <div className="p-8 text-center text-gray-500">
            <Leaf className="w-12 h-12 mx-auto mb-2 text-gray-300" />
            <p>暂无农耕知识，点击上方按钮添加</p>
          </div>
        ) : (
          <div className="divide-y">
            {items.map((item) => (
              <div key={item.id} className="p-4 hover:bg-gray-50">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span
                        className={`px-2 py-0.5 rounded text-xs ${
                          categoryLabels[item.category]?.color || 'bg-gray-100 text-gray-700'
                        }`}
                      >
                        {categoryLabels[item.category]?.label || item.category}
                      </span>
                      {item.solar_term_code && (
                        <span className="px-2 py-0.5 rounded text-xs bg-green-100 text-green-700">
                          {getTermName(item.solar_term_code)}
                        </span>
                      )}
                      {!item.is_active && (
                        <span className="px-2 py-0.5 rounded text-xs bg-red-100 text-red-700">
                          已禁用
                        </span>
                      )}
                    </div>
                    <h3 className="font-semibold text-gray-900">{item.title}</h3>
                    <p className="text-sm text-gray-600 mt-1 line-clamp-2">{item.content}</p>
                  </div>
                  <div className="flex gap-1 ml-4">
                    <button
                      onClick={() => handleEdit(item)}
                      className="p-2 hover:bg-gray-100 rounded"
                      title="编辑"
                    >
                      <Edit2 className="w-4 h-4 text-gray-500" />
                    </button>
                    <button
                      onClick={() => handleDelete(item.id, item.title)}
                      className="p-2 hover:bg-red-50 rounded"
                      title="删除"
                    >
                      <Trash2 className="w-4 h-4 text-red-500" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
