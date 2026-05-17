/**
 * AuthStore — 当前登录用户的轻量缓存
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 5。
 *
 * ⚠️ 真实身份验证由 cookie(httpOnly session)承担,本 store 仅缓存 /me 拉到的用户信息,
 *    用于 UI 显示(用户名、头像、角色)。**不要**把 token 塞这里。
 *
 * TODO(Batch 4 / Frontend-Setup agent):
 *   - 接 useMeQuery(),在 onSuccess 时 setUser
 *   - 监听 'app:unauthorized' 事件,自动 clearUser + 跳 /login
 */
import { create } from 'zustand';

export interface AuthUser {
  id: number | string;
  username: string;
  displayName?: string;
  avatarUrl?: string;
  role?: 'admin' | 'user';
  createdAt?: string;
}

interface AuthState {
  user: AuthUser | null;
  isInitialized: boolean;
  setUser: (user: AuthUser | null) => void;
  clearUser: () => void;
  setInitialized: (v: boolean) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isInitialized: false,
  setUser: (user) => set({ user }),
  clearUser: () => set({ user: null }),
  setInitialized: (isInitialized) => set({ isInitialized }),
}));
