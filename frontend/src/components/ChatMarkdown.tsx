import type { ReactNode } from "react";

import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

type ChatMarkdownProps = {
  markdown: string;
  className?: string;
};

function textFromChildren(children: ReactNode): string {
  if (typeof children === "string") return children;
  if (!Array.isArray(children)) return "";
  return children
    .map((child) => (typeof child === "string" ? child : ""))
    .join("");
}

export function ChatMarkdown({ markdown, className }: ChatMarkdownProps) {
  const text = typeof markdown === "string" ? markdown : "";
  if (!text.trim()) return null;

  return (
    <div
      className={cn(
        "break-words text-sm leading-6 text-foreground",
        className
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        components={{
          p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
          ul: ({ children }) => <ul className="my-2 list-disc pl-6">{children}</ul>,
          ol: ({ children }) => <ol className="my-2 list-decimal pl-6">{children}</ol>,
          li: ({ children }) => <li className="my-1">{children}</li>,
          blockquote: ({ children }) => (
            <blockquote className="my-2 border-l-2 border-border pl-3 text-muted-foreground">
              {children}
            </blockquote>
          ),
          h1: ({ children }) => <h1 className="mb-2 mt-3 text-base font-semibold">{children}</h1>,
          h2: ({ children }) => <h2 className="mb-2 mt-3 text-[15px] font-semibold">{children}</h2>,
          h3: ({ children }) => <h3 className="mb-1 mt-2 text-sm font-semibold">{children}</h3>,
          pre: ({ children }) => (
            <pre className="my-2 overflow-x-auto rounded-md border border-border bg-muted/40 p-3 text-xs leading-relaxed">
              {children}
            </pre>
          ),
          code: ({ children, className: codeClassName, ...props }) => {
            const raw = textFromChildren(children);
            const isBlock =
              (typeof codeClassName === "string" && codeClassName.includes("language-")) ||
              raw.includes("\n");
            if (isBlock) {
              return (
                <code className={cn("font-mono", codeClassName)} {...props}>
                  {children}
                </code>
              );
            }
            return (
              <code
                className={cn(
                  "rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]",
                  codeClassName
                )}
                {...props}
              >
                {children}
              </code>
            );
          },
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="break-all text-primary underline underline-offset-2 transition-opacity hover:opacity-80"
            >
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="my-2 overflow-x-auto">
              <table className="w-full border-collapse text-left text-xs">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border border-border bg-muted/40 px-2 py-1 font-semibold">{children}</th>
          ),
          td: ({ children }) => <td className="border border-border px-2 py-1">{children}</td>,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
