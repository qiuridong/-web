/**
 * 路由表
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 2(路由总览 + 鉴权 guard)、§ 3(页面 wireframe)。
 *
 * 当前批次(6C · 实例 CRUD + 通知 + 设置):
 *   - 公共布局:/login, /setup → <PublicLayout>
 *   - 应用布局:/dashboard, /scripts, /notifications, /settings → <AppLayout>
 *
 * 6C 接入:
 *   - /notifications → <NotificationHub>
 *   - /settings/:tab → <Settings>(默认 tab=account)
 *   - ScriptDetail 已升级(实例 / 历史 / 实时日志 真实功能)
 *
 * 鉴权 loader 策略(设计稿 § 2.2):
 *   - 完整 loader 接 ensureQueryData(...) 模式留给后续批次;
 *   - 本批次先在 Login / Setup 页面内用 useEffect + useSetupStatus 互相跳转,
 *     在 AppLayout 监听 'app:unauthorized' 事件兜底跳 /login。
 *   - 这样能保证现有 placeholder 页面可访问,debug 期间不被强制重定向打断。
 */
import { createBrowserRouter, redirect } from 'react-router';

import { PublicLayout } from '@/components/layout/PublicLayout';
import { AppLayout } from '@/components/layout/AppLayout';
import { Placeholder, NotFoundPage } from '@/components/layout/Placeholder';
import { LoginPage } from '@/pages/auth/Login';
import { SetupPage } from '@/pages/auth/Setup';
import { Dashboard } from '@/pages/dashboard/Dashboard';
import { ScriptList } from '@/pages/scripts/ScriptList';
import { ScriptDetail } from '@/pages/scripts/ScriptDetail';
import { InstanceList } from '@/pages/instances/InstanceList';
import { NodeList } from '@/pages/nodes/NodeList';
import { RunList } from '@/pages/runs/RunList';
import { NotificationHub } from '@/pages/notifications/NotificationHub';
import { Settings } from '@/pages/settings/Settings';

/* ============ 路由表 ============ */

import { RouteErrorBoundary } from '@/components/common/RouteErrorBoundary';

export const router = createBrowserRouter([
  {
    element: <PublicLayout />,
    errorElement: <RouteErrorBoundary />,
    children: [
      { path: '/login', element: <LoginPage /> },
      { path: '/setup', element: <SetupPage /> },
    ],
  },
  {
    path: '/',
    element: <AppLayout />,
    errorElement: <RouteErrorBoundary />,
    children: [
      // / → /dashboard
      { index: true, loader: () => redirect('/dashboard') },
      { path: 'dashboard', element: <Dashboard /> },
      {
        path: 'scripts',
        element: <ScriptList />,
      },
      {
        path: 'scripts/:slug',
        element: <ScriptDetail />,
      },
      {
        path: 'scripts/:slug/instances/:id',
        element: <Placeholder title="Instance Detail" />,
      },
      { path: 'instances', element: <InstanceList /> },
      { path: 'nodes', element: <NodeList /> },
      { path: 'runs', element: <RunList /> },
      { path: 'runs/:id', element: <RunList /> },
      {
        path: 'notifications',
        element: <NotificationHub />,
      },
      {
        path: 'notifications/channels/:id',
        element: <NotificationHub />,
      },
      { path: 'settings', loader: () => redirect('/settings/account') },
      { path: 'settings/:tab', element: <Settings /> },
    ],
  },
  { path: '*', element: <NotFoundPage /> },
]);
