export const paths = {
  dashboard: {
    root: '/dashboard',
    papers: { root: '/dashboard/papers', details: (slug: string) => `/dashboard/papers/${encodeURIComponent(slug)}` },
    terms: '/dashboard/terms',
    topics: '/dashboard/topics',
    vocab: '/dashboard/vocab',
  },
};
