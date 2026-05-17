/**
 * UIStore — 纯客户端 UI 状态(不缓存服务端数据)
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 5(状态管理)。
 *
 * 字段:
 *   - sidebarCollapsed:侧栏折叠状态(persist)
 *   - commandPaletteOpen:⌘K 命令面板开关(不 persist,纯瞬时)
 *   - compactMode:紧凑模式(影响表格行高 / 卡片 padding,persist)
 *
 * 注意:
 *   - 服务端数据走 TanStack Query,不要塞这里
 *   - 跨标签页同步靠 zustand persist 的 storage 事件即可
 */
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

interface UIState {
  sidebarCollapsed: boolean;
  commandPaletteOpen: boolean;
  compactMode: boolean;

  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setCommandPalette: (open: boolean) => void;
  toggleCommandPalette: () => void;
  setCompactMode: (compact: boolean) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      commandPaletteOpen: false,
      compactMode: false,

      toggleSidebar: () =>
        set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      setCommandPalette: (commandPaletteOpen) => set({ commandPaletteOpen }),
      toggleCommandPalette: () =>
        set((state) => ({ commandPaletteOpen: !state.commandPaletteOpen })),
      setCompactMode: (compactMode) => set({ compactMode }),
    }),
    {
      name: 'signin-panel-ui',
      storage: createJSONStorage(() => localStorage),
      // commandPaletteOpen 不 persist(瞬时状态)
      partialize: (state) => ({
        sidebarCollapsed: state.sidebarCollapsed,
        compactMode: state.compactMode,
      }),
      version: 1,
    },
  ),
);
