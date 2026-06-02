/**
 * 「我的管家地址」设置弹窗 —— 货架是公共仓库，访问者填入自己部署的签到管家地址，
 * 之后「导入到管家」就跳到他自己的管家。仅存浏览器 localStorage。
 */
import * as React from 'react';
import { toast } from 'sonner';

import { getManagerUrl, setManagerUrl } from '@/lib/manager';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  /** 保存成功后回调（如保存后自动跳转导入），参数为规范化后的管家地址。 */
  afterSave?: (url: string) => void;
}

export function ManagerSettingsDialog({ open, onOpenChange, afterSave }: Props) {
  const [value, setValue] = React.useState('');

  React.useEffect(() => {
    if (open) setValue(getManagerUrl());
  }, [open]);

  const handleSave = () => {
    const v = value.trim().replace(/\/+$/, '');
    if (v && !/^https?:\/\//i.test(v)) {
      toast.error('请填写完整地址，需含 http:// 或 https://');
      return;
    }
    setManagerUrl(v);
    toast.success(v ? '已保存管家地址' : '已清除管家地址');
    onOpenChange(false);
    if (v && afterSave) afterSave(v);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>设置「我的管家地址」</DialogTitle>
          <DialogDescription>
            货架是公共脚本仓库。填入你自己部署的「签到管家」地址，之后点「导入到管家」
            就会跳到你自己的管家一键导入。仅保存在本浏览器，不上传。
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="manager-url">管家地址</Label>
          <Input
            id="manager-url"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="https://你的管家域名"
            autoFocus
          />
          <p className="text-xs text-muted-foreground">
            还没有管家？用 <code className="rounded bg-muted px-1 font-mono">install-panel.sh</code>{' '}
            在自己的 VPS 一键部署一套（见签到管家仓库）。也可留空，改用每个脚本的「复制 bundle 链接」手动导入。
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSave}>保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
