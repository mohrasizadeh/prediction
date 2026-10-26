// Learn and legal pages: Markdown from /api/public/pages/{slug}. react-markdown does not render raw HTML,
// which is the sanitising rule in docs/15. Do not add rehype-raw.
import ReactMarkdown from "react-markdown";
import { useParams } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { ErrorBox, Loading } from "../components/States";

export default function MarkdownPage({ slug: fixed }) {
  const { slug } = useParams();
  const page = useApi(`/public/pages/${encodeURIComponent(fixed || slug || "learn")}`);
  if (page.loading) return <Loading />;
  if (page.error) return <ErrorBox error={page.error} />;
  return <article className="prose"><h1>{page.data.title}</h1><ReactMarkdown>{page.data.body_md || ""}</ReactMarkdown></article>;
}
