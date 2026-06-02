import * as React from 'react';
import { Check, Copy } from 'lucide-react';
import { toast } from 'sonner';

import { Button, type ButtonProps } from '@/components/ui/button';

interface CopyButtonProps extends Omit<ButtonProps, 'onClick'> {
  value: string;
  label?: string;
  toastMessage?: string;
}

/** 复制文本到剪贴板,带 ✓ 反馈 + toast。 */
export function CopyButton({ value, label, toastMessage, children, ...props }: CopyButtonProps) {
  const [copied, setCopied] = React.useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      toast.success(toastMessage ?? '已复制到剪贴板');
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error('复制失败,请手动复制');
    }
  };

  return (
    <Button onClick={handleCopy} {...props}>
      {copied ? <Check /> : <Copy />}
      {children ?? label}
    </Button>
  );
}
