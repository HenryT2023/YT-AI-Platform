'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft,
  User,
  TrendingUp,
  Clock,
  MessageSquare,
  Award,
  MapPin,
  Tag,
  Calendar,
  Activity,
  Plus,
  X,
} from 'lucide-react';
import Link from 'next/link';

interface VisitorProfile {
  id: string;
  user_id: string;
  tenant_id: string;
  site_id: string;
  visit_count: number;
  total_duration_minutes: number;
  conversation_count: number;
  quest_completed_count: number;
  achievement_count: number;
  check_in_count: number;
  activity_level: string;
  engagement_score: number;
  learning_style: string | null;
  favorite_npc_id: string | null;
  favorite_scene_id: string | null;
  interest_tags: Record<string, any> | null;
  first_visit_at: string;
  last_visit_at: string;
  last_active_at: string;
  notes: string | null;
}

interface VisitorTag {
  id: string;
  tag_type: string;
  tag_key: string;
  tag_value: string;
  confidence: number;
  source: string;
  is_active: boolean;
  created_at: string;
}

interface CheckIn {
  id: string;
  scene_id: string;
  check_in_at: string;
  duration_minutes: number | null;
  photo_count: number;
  interaction_count: number;
}

interface Interaction {
  id: string;
  npc_id: string;
  conversation_count: number;
  message_count: number;
  total_duration_minutes: number;
  sentiment_score: number | null;
  satisfaction_score: number | null;
  last_interaction_at: string;
}

const activityLevelLabels: Record<string, { label: string; color: string }> = {
  new: { label: '新手', color: 'bg-gray-100 text-gray-700' },
  casual: { label: '休闲', color: 'bg-blue-100 text-blue-700' },
  active: { label: '活跃', color: 'bg-green-100 text-green-700' },
  power: { label: '核心', color: 'bg-purple-100 text-purple-700' },
};

const tagTypeLabels: Record<string, string> = {
  interest: '兴趣',
  behavior: '行为',
  achievement: '成就',
  custom: '自定义',
};

export default function VisitorProfileDetailPage() {
  const params = useParams();
  const router = useRouter();
  const profileId = params.id as string;

  const [profile, setProfile] = useState<VisitorProfile | null>(null);
  const [tags, setTags] = useState<VisitorTag[]>([]);
  const [checkIns, setCheckIns] = useState<CheckIn[]>([]);
  const [interactions, setInteractions] = useState<Interaction[]>([]);
  const [loading, setLoading] = useState(true);

  // 新增标签表单
  const [showAddTag, setShowAddTag] = useState(false);
  const [newTag, setNewTag] = useState({
    tag_type: 'interest',
    tag_key: '',
    tag_value: '',
    confidence: 1.0,
  });

  useEffect(() => {
    fetchProfileData();
  }, [profileId]);

  const fetchProfileData = async () => {
    setLoading(true);
    try {
      // 获取画像详情
      const profileRes = await fetch(`/api/admin/visitor-profiles/${profileId}`);
      if (profileRes.ok) {
        const profileData = await profileRes.json();
        setProfile(profileData);
      }

      // 获取标签
      const tagsRes = await fetch(`/api/admin/visitor-profiles/${profileId}/tags`);
      if (tagsRes.ok) {
        const tagsData = await tagsRes.json();
        setTags(tagsData);
      }

      // 获取打卡记录
      const checkInsRes = await fetch(`/api/admin/visitor-profiles/${profileId}/check-ins`);
      if (checkInsRes.ok) {
        const checkInsData = await checkInsRes.json();
        setCheckIns(checkInsData);
      }

      // 获取交互记录
      const interactionsRes = await fetch(`/api/admin/visitor-profiles/${profileId}/interactions`);
      if (interactionsRes.ok) {
        const interactionsData = await interactionsRes.json();
        setInteractions(interactionsData);
      }
    } catch (error) {
      console.error('获取画像数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAddTag = async () => {
    if (!newTag.tag_key || !newTag.tag_value) {
      alert('请填写标签键和标签值');
      return;
    }

    try {
      const res = await fetch(`/api/admin/visitor-profiles/${profileId}/tags`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          profile_id: profileId,
          ...newTag,
          source: 'manual',
        }),
      });

      if (res.ok) {
        setShowAddTag(false);
        setNewTag({ tag_type: 'interest', tag_key: '', tag_value: '', confidence: 1.0 });
        fetchProfileData();
      } else {
        alert('添加标签失败');
      }
    } catch (error) {
      console.error('添加标签失败:', error);
      alert('添加标签失败');
    }
  };

  const handleDeleteTag = async (tagId: string) => {
    if (!confirm('确定要删除这个标签吗？')) return;

    try {
      const res = await fetch(`/api/admin/visitor-profiles/${profileId}/tags/${tagId}`, {
        method: 'DELETE',
      });

      if (res.ok) {
        fetchProfileData();
      } else {
        alert('删除标签失败');
      }
    } catch (error) {
      console.error('删除标签失败:', error);
      alert('删除标签失败');
    }
  };

  const formatDuration = (minutes: number) => {
    if (minutes < 60) return `${minutes}分钟`;
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return `${hours}小时${mins > 0 ? mins + '分钟' : ''}`;
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  if (loading) {
    return (
      <div className="p-6">
        <div className="text-center text-gray-500">加载中...</div>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="p-6">
        <div className="text-center text-gray-500">画像不存在</div>
      </div>
    );
  }

  return (
    <div className="p-6">
      {/* 头部 */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            onClick={() => router.back()}
            className="p-2 hover:bg-gray-100 rounded-lg"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">游客画像详情</h1>
            <p className="text-gray-600 mt-1 font-mono text-sm">ID: {profile.id}</p>
          </div>
        </div>
        <span
          className={`px-3 py-1 text-sm font-medium rounded ${
            activityLevelLabels[profile.activity_level]?.color || 'bg-gray-100 text-gray-700'
          }`}
        >
          {activityLevelLabels[profile.activity_level]?.label || profile.activity_level}
        </span>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center gap-3">
            <Activity className="w-8 h-8 text-blue-500" />
            <div>
              <p className="text-sm text-gray-600">访问次数</p>
              <p className="text-2xl font-bold text-gray-900">{profile.visit_count}</p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center gap-3">
            <Clock className="w-8 h-8 text-green-500" />
            <div>
              <p className="text-sm text-gray-600">停留时长</p>
              <p className="text-lg font-bold text-gray-900">
                {formatDuration(profile.total_duration_minutes)}
              </p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center gap-3">
            <MessageSquare className="w-8 h-8 text-purple-500" />
            <div>
              <p className="text-sm text-gray-600">对话次数</p>
              <p className="text-2xl font-bold text-gray-900">{profile.conversation_count}</p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center gap-3">
            <TrendingUp className="w-8 h-8 text-orange-500" />
            <div>
              <p className="text-sm text-gray-600">参与度</p>
              <p className="text-2xl font-bold text-gray-900">{profile.engagement_score.toFixed(1)}</p>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 左侧：基本信息 */}
        <div className="lg:col-span-2 space-y-6">
          {/* 基本信息卡片 */}
          <div className="bg-white rounded-lg border p-6">
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <User className="w-5 h-5" />
              基本信息
            </h2>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-gray-600">用户 ID</p>
                <p className="font-mono text-sm mt-1">{profile.user_id}</p>
              </div>
              <div>
                <p className="text-sm text-gray-600">学习风格</p>
                <p className="mt-1">{profile.learning_style || '未设置'}</p>
              </div>
              <div>
                <p className="text-sm text-gray-600">首次访问</p>
                <p className="text-sm mt-1">{formatDate(profile.first_visit_at)}</p>
              </div>
              <div>
                <p className="text-sm text-gray-600">最后访问</p>
                <p className="text-sm mt-1">{formatDate(profile.last_visit_at)}</p>
              </div>
              <div>
                <p className="text-sm text-gray-600">完成任务</p>
                <p className="mt-1">{profile.quest_completed_count} 个</p>
              </div>
              <div>
                <p className="text-sm text-gray-600">获得成就</p>
                <p className="mt-1">{profile.achievement_count} 个</p>
              </div>
            </div>
          </div>

          {/* 标签管理 */}
          <div className="bg-white rounded-lg border p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold flex items-center gap-2">
                <Tag className="w-5 h-5" />
                标签 ({tags.length})
              </h2>
              <button
                onClick={() => setShowAddTag(true)}
                className="flex items-center gap-2 px-3 py-1.5 bg-primary-600 text-white rounded-lg hover:bg-primary-700 text-sm"
              >
                <Plus className="w-4 h-4" />
                添加标签
              </button>
            </div>

            {showAddTag && (
              <div className="mb-4 p-4 bg-gray-50 rounded-lg">
                <div className="grid grid-cols-2 gap-3 mb-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">类型</label>
                    <select
                      value={newTag.tag_type}
                      onChange={(e) => setNewTag({ ...newTag, tag_type: e.target.value })}
                      className="w-full border rounded px-3 py-2"
                    >
                      <option value="interest">兴趣</option>
                      <option value="behavior">行为</option>
                      <option value="achievement">成就</option>
                      <option value="custom">自定义</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">置信度</label>
                    <input
                      type="number"
                      value={newTag.confidence}
                      onChange={(e) => setNewTag({ ...newTag, confidence: parseFloat(e.target.value) })}
                      min="0"
                      max="1"
                      step="0.1"
                      className="w-full border rounded px-3 py-2"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">标签键</label>
                    <input
                      type="text"
                      value={newTag.tag_key}
                      onChange={(e) => setNewTag({ ...newTag, tag_key: e.target.value })}
                      placeholder="例如: farming"
                      className="w-full border rounded px-3 py-2"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">标签值</label>
                    <input
                      type="text"
                      value={newTag.tag_value}
                      onChange={(e) => setNewTag({ ...newTag, tag_value: e.target.value })}
                      placeholder="例如: 对农耕文化感兴趣"
                      className="w-full border rounded px-3 py-2"
                    />
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={handleAddTag}
                    className="px-4 py-2 bg-primary-600 text-white rounded hover:bg-primary-700"
                  >
                    确定
                  </button>
                  <button
                    onClick={() => setShowAddTag(false)}
                    className="px-4 py-2 border rounded hover:bg-gray-50"
                  >
                    取消
                  </button>
                </div>
              </div>
            )}

            <div className="space-y-2">
              {tags.length === 0 ? (
                <p className="text-gray-500 text-center py-4">暂无标签</p>
              ) : (
                tags.map((tag) => (
                  <div
                    key={tag.id}
                    className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
                  >
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded">
                          {tagTypeLabels[tag.tag_type] || tag.tag_type}
                        </span>
                        <span className="font-medium">{tag.tag_key}</span>
                        <span className="text-gray-600">: {tag.tag_value}</span>
                      </div>
                      <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
                        <span>置信度: {(tag.confidence * 100).toFixed(0)}%</span>
                        <span>来源: {tag.source}</span>
                        <span>{formatDate(tag.created_at)}</span>
                      </div>
                    </div>
                    <button
                      onClick={() => handleDeleteTag(tag.id)}
                      className="p-1 hover:bg-gray-200 rounded"
                    >
                      <X className="w-4 h-4 text-gray-600" />
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* 打卡记录 */}
          <div className="bg-white rounded-lg border p-6">
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <MapPin className="w-5 h-5" />
              打卡记录 ({checkIns.length})
            </h2>
            <div className="space-y-2">
              {checkIns.length === 0 ? (
                <p className="text-gray-500 text-center py-4">暂无打卡记录</p>
              ) : (
                checkIns.slice(0, 10).map((checkIn) => (
                  <div key={checkIn.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                    <div>
                      <p className="font-medium">场景 ID: {checkIn.scene_id.slice(0, 8)}...</p>
                      <p className="text-sm text-gray-600 mt-1">
                        {formatDate(checkIn.check_in_at)}
                        {checkIn.duration_minutes && ` · ${formatDuration(checkIn.duration_minutes)}`}
                      </p>
                    </div>
                    <div className="text-right text-sm text-gray-600">
                      <p>拍照 {checkIn.photo_count} 次</p>
                      <p>交互 {checkIn.interaction_count} 次</p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* 右侧：交互统计 */}
        <div className="space-y-6">
          <div className="bg-white rounded-lg border p-6">
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <MessageSquare className="w-5 h-5" />
              NPC 交互 ({interactions.length})
            </h2>
            <div className="space-y-3">
              {interactions.length === 0 ? (
                <p className="text-gray-500 text-center py-4">暂无交互记录</p>
              ) : (
                interactions.map((interaction) => (
                  <div key={interaction.id} className="p-3 bg-gray-50 rounded-lg">
                    <p className="font-medium">NPC: {interaction.npc_id.slice(0, 8)}...</p>
                    <div className="mt-2 space-y-1 text-sm text-gray-600">
                      <p>对话 {interaction.conversation_count} 次</p>
                      <p>消息 {interaction.message_count} 条</p>
                      <p>时长 {formatDuration(interaction.total_duration_minutes)}</p>
                      {interaction.sentiment_score !== null && (
                        <p>情感: {(interaction.sentiment_score * 100).toFixed(0)}%</p>
                      )}
                      {interaction.satisfaction_score !== null && (
                        <p>满意度: {interaction.satisfaction_score.toFixed(1)}/5</p>
                      )}
                    </div>
                    <p className="text-xs text-gray-500 mt-2">
                      {formatDate(interaction.last_interaction_at)}
                    </p>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
