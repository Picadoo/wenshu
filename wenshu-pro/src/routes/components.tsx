import { forwardRef } from 'react';
import { Link, type LinkProps } from 'react-router';

export const RouterLink = forwardRef<HTMLAnchorElement, Omit<LinkProps, 'to'> & { href: string }>(function RouterLink({ href, ...props }, ref) {
  return <Link ref={ref} to={href} {...props} />;
});
