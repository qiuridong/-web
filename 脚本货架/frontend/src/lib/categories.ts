/**
 * 预设分类(与货架后端固定 10 个一致)。
 * 后端契约:script.category 为 string | null;PATCH {category:""} 清为未分类。
 */
import {
  BookOpen,
  Clapperboard,
  Cloud,
  Code2,
  Gamepad2,
  type LucideIcon,
  MessagesSquare,
  Network,
  Palette,
  ShoppingCart,
  Tag,
} from 'lucide-react';

/** 固定预设分类(顺序即展示顺序)。 */
export const CATEGORIES = [
  'PT站',
  '影视',
  '漫画动漫',
  '论坛社区',
  '网盘云盘',
  '阅读小说',
  '技术开发',
  '游戏',
  '购物',
  '其他',
] as const;

export type Category = (typeof CATEGORIES)[number];

/** 画廊筛选用的「未分类」哨兵值(对应 category === null)。 */
export const UNCATEGORIZED = '__uncategorized__';

/** 每个分类配一个 lucide 图标(找不到时回落到 Tag)。 */
const CATEGORY_ICONS: Record<string, LucideIcon> = {
  PT站: Network,
  影视: Clapperboard,
  漫画动漫: Palette,
  论坛社区: MessagesSquare,
  网盘云盘: Cloud,
  阅读小说: BookOpen,
  技术开发: Code2,
  游戏: Gamepad2,
  购物: ShoppingCart,
  其他: Tag,
};

/** 取分类图标;传入 null/未知 → Tag。 */
export function categoryIcon(category: string | null | undefined): LucideIcon {
  if (!category) return Tag;
  return CATEGORY_ICONS[category] ?? Tag;
}

/** 是否预设分类。 */
export function isPresetCategory(category: string): boolean {
  return (CATEGORIES as readonly string[]).includes(category);
}
