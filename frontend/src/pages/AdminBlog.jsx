import { useEffect, useState, useCallback, useRef } from "react";
import { toast } from "sonner";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Link from "@tiptap/extension-link";
import Image from "@tiptap/extension-image";
import { Bold, Italic, Heading2, Heading3, List, ListOrdered, Quote, Link2, ImagePlus, Sparkles, Eye } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, errMsg, fmtDate, media } from "@/lib/api";
import { PageHeader, Card, Badge, statusTone, Seo } from "@/components/Common";

const BLANK = { title: "", slug: "", excerpt: "", content_html: "", featured_image_id: null, featured_image_alt: "", categories: [], tags: [], author_slug: "cricanalyze-team",
  seo_title: "", seo_description: "", canonical_url: "", noindex: false, faqs: [], ai_generated: false };

const Toolbar = ({ editor }) => {
  const file = useRef(null);
  if (!editor) return null;
  const b = (on, I, act, label) => <button type="button" aria-label={label} onClick={act} className={`p-2 rounded ${on ? "bg-white/15" : "hover:bg-white/10"}`} data-testid={`tb-${label}`}><I size={16} /></button>;
  const upload = async (f) => { const fd = new FormData(); fd.append("file", f); try { const { data } = await api.post("/admin/blog/images", fd); const alt = window.prompt("Image alt text (describe the image)") || ""; editor.chain().focus().setImage({ src: media(data.url), alt, title: alt }).run(); } catch (e) { toast.error(errMsg(e)); } };
  return (<div className="flex flex-wrap gap-1 border-b border-white/10 p-1">
    {b(editor.isActive("heading", { level: 2 }), Heading2, () => editor.chain().focus().toggleHeading({ level: 2 }).run(), "h2")}
    {b(editor.isActive("heading", { level: 3 }), Heading3, () => editor.chain().focus().toggleHeading({ level: 3 }).run(), "h3")}
    {b(editor.isActive("bold"), Bold, () => editor.chain().focus().toggleBold().run(), "bold")}
    {b(editor.isActive("italic"), Italic, () => editor.chain().focus().toggleItalic().run(), "italic")}
    {b(editor.isActive("bulletList"), List, () => editor.chain().focus().toggleBulletList().run(), "bullets")}
    {b(editor.isActive("orderedList"), ListOrdered, () => editor.chain().focus().toggleOrderedList().run(), "numbers")}
    {b(editor.isActive("blockquote"), Quote, () => editor.chain().focus().toggleBlockquote().run(), "quote")}
    {b(editor.isActive("link"), Link2, () => { const u = window.prompt("Link URL (use /blog/slug for internal links)"); if (u === null) return; u ? editor.chain().focus().setLink({ href: u }).run() : editor.chain().focus().unsetLink().run(); }, "link")}
    {b(false, ImagePlus, () => file.current.click(), "image")}<input ref={file} type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files[0] && upload(e.target.files[0])} />
  </div>);
};

const Editor = ({ id, back }) => {
  const [p, setP] = useState(null);
  const [meta, setMeta] = useState({ categories: [], authors: [] });
  const [ai, setAi] = useState({ action: "outline", topic: "", result: "" });
  const [aiBusy, setAiBusy] = useState(false);
  const [saved, setSaved] = useState(null);
  const [sched, setSched] = useState("");
  const editor = useEditor({ extensions: [StarterKit.configure({ link: false }), Link.configure({ openOnClick: false }), Image], content: "", editorProps: { attributes: { class: "prose-blog p-4" } } });
  const load = useCallback(async () => { const { data } = await api.get(`/admin/blog/posts/${id}`); setP({ ...BLANK, ...data, tags: data.tags || [] }); editor?.commands.setContent(data.autosave?.content_html || data.content_html || ""); if (data.autosave) toast.info("Restored unsaved autosave draft."); }, [id, editor]);
  useEffect(() => { api.get("/blog/meta").then(({ data }) => setMeta(data)); }, []);
  useEffect(() => { if (editor) load(); }, [editor, load]);
  useEffect(() => {
    const t = setInterval(() => { if (editor && p) api.post(`/admin/blog/posts/${id}/autosave`, { title: p.title, content_html: editor.getHTML() }).then(() => setSaved(new Date())).catch(() => {}); }, 20000);
    return () => clearInterval(t);
  }, [editor, p, id]);
  if (!p) return "Loading…";
  const body = () => { const { id: _i, status, created_at, updated_at, published_at, publish_at, revisions, autosave, created_by, approved_by, ...rest } = p; return { ...rest, content_html: editor.getHTML(), tags: rest.tags }; };
  const save = async () => { try { const { data } = await api.put(`/admin/blog/posts/${id}`, body()); toast.success("Saved."); setP({ ...p, slug: data.slug }); return true; } catch (e) { toast.error(errMsg(e)); return false; } };
  const status = async (action) => { if (!(await save())) return; try { await api.post(`/admin/blog/posts/${id}/status`, { action, publish_at: action === "schedule" ? new Date(sched).toISOString() : null }); toast.success(`Post ${action}ed.`); load(); } catch (e) { toast.error(errMsg(e)); } };
  const runAi = async () => { setAiBusy(true); try { const { data } = await api.post("/admin/blog/ai", { action: ai.action, topic: ai.topic || p.title, content: editor.getHTML() }); setAi({ ...ai, result: data.result }); } catch (e) { toast.error(errMsg(e)); } finally { setAiBusy(false); } };
  const insertAi = () => {
    if (ai.action === "seo") { const t = ai.result.match(/TITLE:\s*(.*)/i)?.[1]; const d = ai.result.match(/DESCRIPTION:\s*(.*)/i)?.[1]; setP({ ...p, seo_title: (t || "").slice(0, 70), seo_description: (d || "").slice(0, 170), ai_generated: true }); }
    else if (ai.action === "grammar" || ai.action === "draft") { editor.commands.setContent(ai.result); setP({ ...p, ai_generated: true }); }
    else { editor.commands.insertContent(ai.result); setP({ ...p, ai_generated: true }); }
    toast.info("Inserted into the draft. Review before publishing.");
  };
  const upFeatured = async (f) => { const fd = new FormData(); fd.append("file", f); try { const { data } = await api.post("/admin/blog/images", fd); setP({ ...p, featured_image_id: data.id }); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <div className="grid lg:grid-cols-3 gap-6" data-testid="blog-editor">
      <div className="lg:col-span-2 space-y-4">
        <div className="flex flex-wrap gap-2 items-center"><Button variant="ghost" onClick={back} data-testid="editor-back-btn">← All posts</Button><Badge tone={statusTone(p.status)}>{p.status}</Badge>{p.ai_generated && <Badge tone="amber">contains AI content — needs editor approval</Badge>}
          <span className="text-xs text-slate-500">{saved ? `Autosaved ${saved.toLocaleTimeString()}` : "Autosaves every 20s"}</span></div>
        <Input className="text-2xl h-14 font-display font-bold" placeholder="Article title" value={p.title} onChange={(e) => setP({ ...p, title: e.target.value })} data-testid="post-title-input" />
        <div className="flex gap-2 items-center text-sm text-slate-400">/blog/<Input value={p.slug} onChange={(e) => setP({ ...p, slug: e.target.value })} className="h-8" data-testid="post-slug-input" /></div>
        <Textarea placeholder="Excerpt (shown on listing pages)" value={p.excerpt} onChange={(e) => setP({ ...p, excerpt: e.target.value })} maxLength={400} data-testid="post-excerpt-input" />
        <div className="glass rounded-xl"><Toolbar editor={editor} /><EditorContent editor={editor} data-testid="post-content-editor" /></div>
        <Card><h3 className="font-semibold mb-3 flex items-center gap-2"><Sparkles size={16} />AI writing assistant</h3><div className="flex flex-wrap gap-2">
          <Select value={ai.action} onValueChange={(v) => setAi({ ...ai, action: v, result: "" })}><SelectTrigger className="w-44" data-testid="ai-action-select"><SelectValue /></SelectTrigger><SelectContent>{[["outline", "Outline"], ["draft", "Full draft"], ["grammar", "Fix grammar"], ["seo", "SEO title & description"], ["faq", "FAQs"], ["social", "Social captions"]].map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent></Select>
          <Input placeholder="Topic (defaults to title)" value={ai.topic} onChange={(e) => setAi({ ...ai, topic: e.target.value })} className="flex-1 min-w-[180px]" data-testid="ai-topic-input" />
          <Button onClick={runAi} disabled={aiBusy} data-testid="ai-run-btn">{aiBusy ? "Writing…" : "Generate"}</Button></div>
          {ai.result && <div className="mt-3"><pre className="whitespace-pre-wrap text-xs bg-black/30 rounded-lg p-3 max-h-60 overflow-y-auto" data-testid="ai-result">{ai.result}</pre>{ai.action !== "social" && <Button size="sm" className="mt-2" onClick={insertAi} data-testid="ai-insert-btn">Insert into draft</Button>}</div>}
          <p className="text-xs text-slate-500 mt-2">AI content stays a draft until an editor publishes it.</p></Card>
      </div>
      <div className="space-y-4">
        <Card className="space-y-2"><h3 className="font-semibold">Publish</h3><div className="flex flex-wrap gap-2"><Button size="sm" onClick={save} variant="secondary" data-testid="post-save-btn">Save draft</Button>
          <Button size="sm" className="bg-[#10B981] text-[#0B132B]" onClick={() => status("publish")} data-testid="post-publish-btn">Publish</Button>
          {p.status === "published" && <Button size="sm" variant="secondary" onClick={() => status("unpublish")} data-testid="post-unpublish-btn">Unpublish</Button>}
          <Button size="sm" variant="ghost" onClick={() => status("archive")} data-testid="post-archive-btn">Archive</Button>
          <Button size="sm" variant="ghost" asChild><a href={`/blog/${p.slug}?preview=1`} target="_blank" rel="noreferrer" data-testid="post-preview-link"><Eye size={14} className="mr-1" />Preview</a></Button></div>
          <div className="flex gap-2 pt-2"><Input type="datetime-local" value={sched} onChange={(e) => setSched(e.target.value)} className="h-8" data-testid="post-schedule-input" /><Button size="sm" variant="secondary" disabled={!sched} onClick={() => status("schedule")} data-testid="post-schedule-btn">Schedule</Button></div>
          {p.publish_at && p.status === "scheduled" && <p className="text-xs text-amber-300">Scheduled for {new Date(p.publish_at).toLocaleString("en-IN")}</p>}</Card>
        <Card className="space-y-2"><h3 className="font-semibold">Featured image</h3>{p.featured_image_id && <img src={media(`/api/blog/images/${p.featured_image_id}`)} alt={p.featured_image_alt} className="rounded-lg" />}
          <input type="file" accept="image/*" onChange={(e) => e.target.files[0] && upFeatured(e.target.files[0])} className="text-xs" data-testid="featured-image-input" />
          <Input placeholder="Alt text / caption" value={p.featured_image_alt} onChange={(e) => setP({ ...p, featured_image_alt: e.target.value })} data-testid="featured-alt-input" /></Card>
        <Card className="space-y-2"><h3 className="font-semibold">Categories</h3><div className="max-h-44 overflow-y-auto space-y-1">{meta.categories.map((c) => <label key={c.slug} className="flex gap-2 text-sm items-center"><Checkbox checked={p.categories.includes(c.slug)} onCheckedChange={(v) => setP({ ...p, categories: v ? [...p.categories, c.slug] : p.categories.filter((x) => x !== c.slug) })} data-testid={`cat-${c.slug}`} />{c.name}</label>)}</div>
          <Input placeholder="Tags, comma separated" value={p.tags.join(", ")} onChange={(e) => setP({ ...p, tags: e.target.value.split(",").map((t) => t.trim()).filter(Boolean) })} data-testid="post-tags-input" />
          <Select value={p.author_slug} onValueChange={(v) => setP({ ...p, author_slug: v })}><SelectTrigger data-testid="post-author-select"><SelectValue /></SelectTrigger><SelectContent>{meta.authors.map((a) => <SelectItem key={a.slug} value={a.slug}>{a.name}</SelectItem>)}</SelectContent></Select></Card>
        <Card className="space-y-2"><h3 className="font-semibold">SEO</h3><Input placeholder={`SEO title (${p.seo_title.length}/70)`} maxLength={70} value={p.seo_title} onChange={(e) => setP({ ...p, seo_title: e.target.value })} data-testid="post-seo-title" />
          <Textarea placeholder={`Meta description (${p.seo_description.length}/170)`} maxLength={170} value={p.seo_description} onChange={(e) => setP({ ...p, seo_description: e.target.value })} data-testid="post-seo-desc" />
          <Input placeholder="Canonical URL (optional)" value={p.canonical_url} onChange={(e) => setP({ ...p, canonical_url: e.target.value })} />
          <label className="flex justify-between text-sm">Noindex<Switch checked={p.noindex} onCheckedChange={(v) => setP({ ...p, noindex: v })} data-testid="post-noindex" /></label></Card>
        {p.revisions?.length > 0 && <Card><h3 className="font-semibold mb-2">Revisions</h3>{p.revisions.map((r) => <p key={r.id} className="text-xs text-slate-400">{new Date(r.created_at).toLocaleString("en-IN")} — {r.title}</p>)}</Card>}
      </div>
    </div>
  );
};

export default function AdminBlog() {
  const [status, setStatus] = useState("all");
  const [posts, setPosts] = useState(null);
  const [edit, setEdit] = useState(null);
  const [redirects, setRedirects] = useState([]);
  const [rd, setRd] = useState({ from_slug: "", to_slug: "" });
  const [newCat, setNewCat] = useState("");
  const load = useCallback(() => { api.get("/admin/blog/posts", { params: status === "all" ? {} : { status } }).then(({ data }) => setPosts(data)); api.get("/admin/blog/redirects").then(({ data }) => setRedirects(data)); }, [status]);
  useEffect(() => { load(); }, [load]);
  const create = async () => { try { const { data } = await api.post("/admin/blog/posts", { ...BLANK, title: "Untitled article" }); setEdit(data.id); } catch (e) { toast.error(errMsg(e)); } };
  if (edit) return <div><Seo title="Edit post" path="/admin/blog" noindex /><Editor id={edit} back={() => { setEdit(null); load(); }} /></div>;
  return (
    <div><Seo title="Blog CMS" path="/admin/blog" noindex />
      <PageHeader eyebrow="Content" title="Blog CMS" desc="Drafts and previews are never public or indexed. Scheduled posts publish automatically on the server.">
        <Button onClick={create} className="bg-[#10B981] text-[#0B132B]" data-testid="new-post-btn">New article</Button></PageHeader>
      <div className="flex gap-2 mb-4 flex-wrap">{["all", "draft", "scheduled", "published", "archived"].map((s) => <Button key={s} size="sm" variant={status === s ? "default" : "secondary"} onClick={() => setStatus(s)} data-testid={`filter-${s}`}>{s}</Button>)}</div>
      <div className="glass rounded-xl divide-y divide-white/5 mb-8" data-testid="admin-post-list">{(posts || []).map((p) => <div key={p.id} className="flex flex-wrap justify-between items-center gap-2 p-4">
        <div><button className="font-medium hover:text-[#00B4D8] text-left" onClick={() => setEdit(p.id)} data-testid={`edit-post-${p.slug}`}>{p.title}</button><div className="text-xs text-slate-500">/blog/{p.slug} · updated {fmtDate(p.updated_at)}</div></div>
        <div className="flex gap-1 items-center"><Badge tone={statusTone(p.status)}>{p.status}</Badge>
          <Button size="sm" variant="ghost" onClick={async () => { await api.post(`/admin/blog/posts/${p.id}/duplicate`); load(); }} data-testid={`dup-post-${p.slug}`}>Duplicate</Button>
          <Button size="sm" variant="ghost" className="text-red-300" onClick={async () => { if (window.confirm("Delete this article permanently?")) { await api.delete(`/admin/blog/posts/${p.id}`); load(); } }} data-testid={`del-post-${p.slug}`}>Delete</Button></div></div>)}
        {posts && !posts.length && <p className="p-4 text-sm text-slate-500">No articles.</p>}</div>
      <div className="grid md:grid-cols-2 gap-5">
        <Card><h3 className="font-semibold mb-3">Redirects</h3><div className="flex gap-2"><Input placeholder="old-slug" value={rd.from_slug} onChange={(e) => setRd({ ...rd, from_slug: e.target.value })} /><Input placeholder="new-slug" value={rd.to_slug} onChange={(e) => setRd({ ...rd, to_slug: e.target.value })} />
          <Button size="sm" onClick={async () => { await api.post("/admin/blog/redirects", rd); setRd({ from_slug: "", to_slug: "" }); load(); }} disabled={!rd.from_slug || !rd.to_slug} data-testid="add-redirect-btn">Add</Button></div>
          {redirects.map((r) => <div key={r.from_slug} className="flex justify-between text-xs mt-2"><span>/blog/{r.from_slug} → /blog/{r.to_slug}</span><button className="text-red-300" onClick={async () => { await api.delete(`/admin/blog/redirects/${r.from_slug}`); load(); }}>Remove</button></div>)}
          <p className="text-xs text-slate-500 mt-2">Changing a published post's slug creates a redirect automatically.</p></Card>
        <Card><h3 className="font-semibold mb-3">Add category</h3><div className="flex gap-2"><Input value={newCat} onChange={(e) => setNewCat(e.target.value)} placeholder="Category name" data-testid="new-category-input" />
          <Button size="sm" onClick={async () => { try { await api.post("/admin/blog/taxonomy/categories", { name: newCat }); setNewCat(""); toast.success("Added."); } catch (e) { toast.error(errMsg(e)); } }} disabled={newCat.length < 2} data-testid="add-category-btn">Add</Button></div></Card>
      </div>
    </div>
  );
}
