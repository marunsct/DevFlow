import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';

/**
 * The one place Markdown becomes styled HTML.
 *
 * Every element is given explicit classes rather than relying on Tailwind's
 * `prose`: the typography plugin that defines those classes is not installed,
 * so the `prose prose-invert` strings dotted around the app were inert and
 * their Markdown rendered with default browser styles - serif headings and
 * hairline tables on a dark background.
 *
 * `remark-gfm` is what makes tables, strikethrough and task lists work. Agents
 * emit GFM tables routinely (a verification matrix, a comparison of options),
 * and without it those arrive as a wall of pipe characters.
 */

type Density = 'compact' | 'document';

interface MarkdownProps {
  children: string;
  /** `compact` for the activity feed, `document` for a full artifact. */
  density?: Density;
  className?: string;
}

const buildComponents = (density: Density): Components => {
  const compact = density === 'compact';
  const text = compact ? 'text-[13px]' : 'text-sm';

  return {
    p: ({ children }) => (
      <p className={`${text} leading-relaxed text-text-primary mb-2 last:mb-0`}>{children}</p>
    ),
    strong: ({ children }) => <strong className="font-semibold text-text-primary">{children}</strong>,
    em: ({ children }) => <em className="italic text-text-secondary">{children}</em>,
    del: ({ children }) => <del className="text-text-muted line-through">{children}</del>,

    a: ({ children, href }) => (
      <a
        href={href}
        target="_blank"
        rel="noreferrer noopener"
        className="text-primary underline underline-offset-2 hover:text-primary-hover break-words"
      >
        {children}
      </a>
    ),

    h1: ({ children }) => (
      <h1 className={`${compact ? 'text-sm' : 'text-lg'} font-semibold text-text-primary mt-4 first:mt-0 mb-2`}>{children}</h1>
    ),
    h2: ({ children }) => (
      <h2 className={`${compact ? 'text-[13px]' : 'text-base'} font-semibold text-text-primary mt-4 first:mt-0 mb-1.5`}>{children}</h2>
    ),
    h3: ({ children }) => (
      <h3 className={`${text} font-semibold text-text-primary mt-3 first:mt-0 mb-1`}>{children}</h3>
    ),
    h4: ({ children }) => (
      <h4 className={`${text} font-semibold text-text-primary mt-3 first:mt-0 mb-1`}>{children}</h4>
    ),

    ul: ({ children }) => (
      <ul className={`${text} list-disc pl-5 space-y-1 text-text-primary mb-2 last:mb-0 marker:text-text-muted`}>{children}</ul>
    ),
    ol: ({ children }) => (
      <ol className={`${text} list-decimal pl-5 space-y-1 text-text-primary mb-2 last:mb-0 marker:text-text-muted`}>{children}</ol>
    ),
    li: ({ children }) => <li className="leading-relaxed">{children}</li>,

    blockquote: ({ children }) => (
      <blockquote className="border-l-2 border-border pl-3 italic text-text-secondary my-2">{children}</blockquote>
    ),
    hr: () => <hr className="my-3 border-border/50" />,

    // `inline` was removed from the props in react-markdown v10; a block of code
    // arrives wrapped in <pre>, so an inline span is simply one with no newline.
    code: ({ children, className }) => {
      const content = String(children ?? '');
      const isBlock = className?.startsWith('language-') || content.includes('\n');
      if (isBlock) {
        return (
          <code className="block font-mono text-[12px] leading-relaxed text-text-primary whitespace-pre">
            {children}
          </code>
        );
      }
      return (
        <code className="rounded bg-overlay-strong px-1 py-0.5 font-mono text-[0.9em] text-primary break-words">
          {children}
        </code>
      );
    },
    pre: ({ children }) => (
      // Its own scroller: a long line of code must not widen the panel it is in.
      <pre tabIndex={0} className="my-2 overflow-x-auto rounded-lg border border-border bg-inset p-3">{children}</pre>
    ),

    // Tables are wrapped rather than styled in place. An agent's verification
    // matrix is routinely wider than a 23rem rail, and without a scroller of its
    // own it stretches the grid column and pushes the layout sideways.
    table: ({ children }) => (
      <div tabIndex={0} className="my-2 overflow-x-auto rounded-lg border border-border/50">
        {/* A minimum width in the narrow column, deliberately wider than the
            column itself. Left to fit, a four-column verification matrix
            squeezed each cell to a few characters and turned every row into a
            paragraph-tall stack. Keeping the columns legible and scrolling
            sideways is the readable trade. */}
        <table
          className={`w-full border-collapse text-left text-[12px] ${compact ? 'min-w-[26rem]' : ''}`}
        >
          {children}
        </table>
      </div>
    ),
    thead: ({ children }) => <thead className="bg-overlay">{children}</thead>,
    tbody: ({ children }) => <tbody className="divide-y divide-border/40">{children}</tbody>,
    tr: ({ children }) => <tr>{children}</tr>,
    th: ({ children }) => (
      <th className="px-2.5 py-1.5 font-semibold text-text-primary whitespace-nowrap">{children}</th>
    ),
    td: ({ children }) => (
      <td className="px-2.5 py-1.5 align-top text-text-secondary">{children}</td>
    ),

    img: ({ src, alt }) => (
      <img src={typeof src === 'string' ? src : undefined} alt={alt ?? ''} loading="lazy" className="my-2 max-w-full rounded-lg" />
    ),
  };
};

const COMPONENTS: Record<Density, Components> = {
  compact: buildComponents('compact'),
  document: buildComponents('document'),
};

export const Markdown: React.FC<MarkdownProps> = ({ children, density = 'compact', className }) => (
  // `break-words` on the container, because a model will happily emit a
  // 200-character path or URL and nothing below should be able to widen a panel.
  <div className={`min-w-0 break-words ${className ?? ''}`}>
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTS[density]}>
      {children}
    </ReactMarkdown>
  </div>
);
