import Link from "next/link";
import { ArrowLeft, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/**
 * The one page-opening block in the workspace: a brass eyebrow, a serif
 * display title, a short abstract and the page's own actions, closed by a
 * hairline. Pages supply content only, so every route opens with the same
 * rhythm instead of a different arrangement of heading and buttons.
 */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  back,
  icon: Icon,
}: {
  eyebrow: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  back?: { href: string; label: string };
  icon?: LucideIcon;
}) {
  return (
    <header className="page-head">
      <div className="page-head-copy">
        {back && (
          <Link className="page-head-back" href={back.href}>
            <ArrowLeft aria-hidden /> {back.label}
          </Link>
        )}
        <p className="page-head-eyebrow">
          {Icon && <Icon aria-hidden className="size-3" />}
          {eyebrow}
        </p>
        <h1>{title}</h1>
        {description && <p className="page-head-description">{description}</p>}
      </div>
      {actions && <div className="page-head-actions">{actions}</div>}
    </header>
  );
}
