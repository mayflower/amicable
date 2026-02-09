export type TemplateId =
  | "vite"
  | "nextjs15"
  | "fastapi"
  | "hono"
  | "remix"
  | "nuxt3"
  | "sveltekit"
  | "laravel";

export const TEMPLATES: Array<{
  id: TemplateId;
  title: string;
  description: string;
}> = [
  {
    id: "vite",
    title: "Single-Page App",
    description: "Best for landing pages, dashboards, and client-side apps. React + Vite + Tailwind + shadcn/ui.",
  },
  {
    id: "nextjs15",
    title: "Full-Stack Web App",
    description: "Best for SEO, server rendering, and production sites. Next.js 15 App Router + TypeScript.",
  },
  {
    id: "fastapi",
    title: "Python API",
    description: "Best for data pipelines, ML endpoints, and backend services. FastAPI + Python.",
  },
  {
    id: "hono",
    title: "Lightweight API",
    description: "Best for webhooks, edge functions, and small services. Hono + TypeScript.",
  },
  {
    id: "remix",
    title: "Multi-Page App",
    description: "Best for forms, auth flows, and multi-page apps with server logic. React Router (Remix).",
  },
  {
    id: "nuxt3",
    title: "Vue Full-Stack App",
    description: "Best for teams preferring Vue and Nuxt conventions. Nuxt 3 + Vite.",
  },
  {
    id: "sveltekit",
    title: "SvelteKit Full-Stack App",
    description: "Best for fast iteration and small-to-medium full-stack apps. SvelteKit + Vite.",
  },
  {
    id: "laravel",
    title: "Laravel Full-Stack App",
    description: "Best for PHP ecosystems and traditional MVC apps. Laravel + PHP.",
  },
];

export const templateLabel = (id: string | null | undefined): string => {
  const normalized = id === "lovable_vite" ? "vite" : id;
  const found = TEMPLATES.find((t) => t.id === normalized);
  return found ? found.title : "Single-Page App";
};
