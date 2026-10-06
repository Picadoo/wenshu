import { Icon } from '@iconify/react';

export function Iconify({ icon, width = 20 }: { icon: string; width?: number }) {
  return <Icon icon={icon} width={width} height={width} aria-hidden="true" />;
}
