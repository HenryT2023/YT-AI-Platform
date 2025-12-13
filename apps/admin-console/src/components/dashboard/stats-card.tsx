import { LucideIcon } from 'lucide-react';
import clsx from 'clsx';

interface StatsCardProps {
  title: string;
  value: string;
  change: string;
  changeType: 'increase' | 'decrease' | 'neutral';
  icon: LucideIcon;
}

export function StatsCard({
  title,
  value,
  change,
  changeType,
  icon: Icon,
}: StatsCardProps) {
  return (
    <div className="rounded-lg border bg-white p-6 shadow-sm">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">{title}</p>
          <p className="mt-1 text-3xl font-semibold text-gray-900">{value}</p>
        </div>
        <div className="rounded-full bg-primary-50 p-3">
          <Icon className="h-6 w-6 text-primary-600" />
        </div>
      </div>
      <div className="mt-4">
        <span
          className={clsx(
            'text-sm font-medium',
            changeType === 'increase' && 'text-green-600',
            changeType === 'decrease' && 'text-red-600',
            changeType === 'neutral' && 'text-gray-500'
          )}
        >
          {change}
        </span>
        <span className="text-sm text-gray-500"> 较昨日</span>
      </div>
    </div>
  );
}
