import { lazy, Suspense, useCallback, useEffect, useRef, useState, useDeferredValue } from 'react';
import { Link, NavLink, Navigate, Route, Routes, useParams, useSearchParams } from 'react-router';
import DOMPurify from 'dompurify';
import { papers, topicDocs, getPaper, getTopicDoc, filterPapers, paperStats, type Paper } from './data/papers';
import { terms, getTerm, searchTerms } from './data/terms';
import { hydrateVaultData, useVaultEpoch } from './data/hydrate-vault';
import { useVaultText } from './hooks/use-vault-text';
import { useReadingProgress } from './hooks/use-reading-progress';
import { Lightbox } from './components/lightbox';
import { loadPaperData, savePaperData, hydrateFromBackend, flushNotesBackend, type PaperUserData } from './lib/notes-store';
import { loadRecentSessions } from './lib/reader-session';
import { isTauri, initTauriNotesBackend, chooseVaultDir, chooseWebVaultDir, getVaultDir, getWebVaultDir, migrateLocalToVault } from './lib/notes-store-tauri';
import { loadVocabBook, subscribeVocabBook, importPaperVocab, patchVocabEntry, removeVocabWord, enrichVocabBook, type VocabBookEntry } from './lib/vocab-book';
import { loadAiConfig, saveAiConfig, fetchAiModels, REASONING_EFFORT_OPTIONS } from './lib/ai-config';
import { loadHoverTips, loadTermLinks, setHoverTips, setTermLinks } from './lib/reader-prefs';
import { loadServerConfig, saveServerConfig } from './lib/runtime-config';
import { initCloudSync, stopCloudSync } from './lib/cloud-sync';
import client from './lib/axios';
import { copyText } from './utils/copy-text';
import { type MarkdownHeading } from './lib/markdown';
import { appRouteUrl } from './lib/app-env';

const labels = [['/dashboard', '工作台'], ['/dashboard/papers', '论文库'], ['/dashboard/terms', '术语'], ['/dashboard/topics', '专题'], ['/dashboard/vocab', '生词本'], ['/settings', '设置']];
const importGuide = 'https://github.com/Picadoo/wenshu/blob/main/docs/PDF_IMPORT.md';
const MarkdownNote = lazy(() => import('./sections/paper/markdown-note').then((module) => ({ default: module.MarkdownNote })));
function errorText(error: unknown) { return error instanceof Error ? error.message : '操作失败，请检查配置与连接'; }
function escapeHtml(text: string) { return text.replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]!); }
function downloadJson(name: string, data: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
  const link = document.createElement('a'); link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function App() {
  const epoch = useVaultEpoch();
  const [ready, setReady] = useState(false);
  const [message, setMessage] = useState('');
  useEffect(() => {
    let alive = true;
    Promise.all([hydrateVaultData(), initTauriNotesBackend()]).then(() => { if (alive) setReady(true); }).catch((error) => { if (alive) { setReady(true); setMessage(errorText(error)); } });
    const onSaveError = (event: Event) => setMessage((event as CustomEvent<string>).detail);
    window.addEventListener('wenshu-save-error', onSaveError);
    return () => { alive = false; window.removeEventListener('wenshu-save-error', onSaveError); };
  }, []);
  return <>
    <header className="app-header" data-tauri-drag-region>
      <Link to="/dashboard" className="brand">文枢 <small>Wenshu</small></Link>
      <span className="header-note" data-tauri-drag-region>阅读 · 理解 · 积累</span>
      <button onClick={() => hydrateVaultData().then(() => setMessage('目录已刷新')).catch((error) => setMessage(errorText(error)))}>刷新目录</button>
      {isTauri() ? <WindowButtons /> : null}
    </header>
    <nav className="app-nav" aria-label="主导航">{labels.map(([href, label]) => <NavLink key={href} to={href} end={href === '/dashboard'}>{label}</NavLink>)}</nav>
    {message ? <div role="status" className="status"><span>{message}</span><button onClick={() => setMessage('')} aria-label="关闭消息">×</button></div> : null}
    <main className="app-main" data-vault-epoch={epoch}>
      <Suspense fallback={<p role="status">正在加载阅读器…</p>}>{!ready ? <p role="status">正在读取文库…</p> : <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Overview />} />
        <Route path="/dashboard/import" element={<ImportPage />} />
        <Route path="/dashboard/papers" element={<PaperList />} />
        <Route path="/dashboard/papers/:slug" element={<ReaderRoute />} />
        <Route path="/dashboard/terms" element={<TermsPage />} />
        <Route path="/dashboard/topics" element={<TopicsPage />} />
        <Route path="/dashboard/topics/:slug" element={<TopicPage />} />
        <Route path="/dashboard/vocab" element={<VocabPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/admin/users" element={<AdminPage />} />
        <Route path="/share/:token" element={<SharedPaperPage />} />
        <Route path="*" element={<p>找不到页面。<Link to="/dashboard">返回首页</Link></p>} />
      </Routes>}</Suspense>
    </main>
  </>;
}
function WindowButtons() {
  const act = async (action: 'minimize' | 'toggleMaximize' | 'close') => {
    const { getCurrentWindow } = await import('@tauri-apps/api/window'); await getCurrentWindow()[action]();
  };
  return <div className="window-buttons"><button aria-label="最小化" onClick={() => void act('minimize')}>−</button><button aria-label="最大化或还原" onClick={() => void act('toggleMaximize')}>□</button><button aria-label="关闭窗口" onClick={() => void act('close')}>×</button></div>;
}
function Overview() {
  const stats = paperStats();
  const recent = loadRecentSessions().filter((item) => getPaper(item.slug));
  return <><div className="workspace-heading"><div><h1>我的文库</h1><p className="muted">管理论文、继续阅读，整理你的研究笔记。</p></div><div className="workspace-actions"><Link className="button-link primary" to="/dashboard/import">添加论文</Link><Link className="button-link" to="/dashboard/papers">浏览文库</Link></div></div>
    <div className="stats"><article><strong>{stats.total}</strong>篇论文</article><article><strong>{stats.withTranslation}</strong>篇双语正文</article><article><strong>{terms.length}</strong>个术语</article><article><strong>{topicDocs.length}</strong>篇专题</article></div>
    {papers.length ? <><section className="panel"><h2>最近阅读</h2>{recent.length ? recent.map((item) => <p key={item.slug}><Link to={`/dashboard/papers/${encodeURIComponent(item.slug)}?tab=${item.tab}`}>{item.title || item.slug}</Link></p>) : <p>打开一篇论文后，阅读位置会保存在这里。<Link to="/dashboard/papers">前往论文库</Link></p>}</section>
    <section><h2>论文</h2><div className="paper-list">{papers.slice(0, 6).map((paper) => <PaperCard key={paper.slug} paper={paper} />)}</div></section></> : <section className="panel"><h2>还没有论文</h2><p>添加你的第一篇论文，开始整理自己的文库。</p><Link className="button-link primary" to="/dashboard/import">添加论文</Link></section>}
  </>;
}
function ImportPage() {
  const [path, setPath] = useState('');
  const [message, setMessage] = useState('');
  const instruction = `按 skills/paper-ingest/SKILL.md 将 ${path.trim() || '我的 PDF'} 导入文枢：先查重，核对完整原文、图表和公式，再生成完整译文与学习笔记，通过验收后同步到我的文库。保留原 PDF。`;
  return <><h1>添加论文</h1><p className="muted">使用本机入库工具整理 PDF，完成后在文库中阅读。</p><section className="panel settings"><h2>交给 AI 助手整理</h2><p>当前入库流程由本机的 AI 助手执行，网页不会把文件上传到公共服务。</p><label>本机 PDF 路径<input value={path} onChange={(event) => setPath(event.target.value)} placeholder="填写要整理的 PDF 文件路径" /></label><textarea aria-label="入库指令" value={instruction} readOnly rows={5} /><button onClick={async () => setMessage(await copyText(instruction) ? '已复制，请将指令交给本机 AI 助手' : '请手动复制入库指令')}>复制入库指令</button>{message ? <p role="status">{message}</p> : null}<a href={importGuide} target="_blank" rel="noreferrer">工具安装与完整导入步骤</a></section><section className="panel"><h2>完成后打开文库</h2><p>入库工具会同步正文、译文、图片和原 PDF。刷新目录后，新论文会出现在论文库中。</p><div className="workspace-actions"><button onClick={() => hydrateVaultData().then(() => setMessage('目录已刷新')).catch((error) => setMessage(errorText(error)))}>刷新目录</button><Link className="button-link" to="/dashboard/papers">前往论文库</Link></div></section></>;
}
function PaperCard({ paper }: { paper: Paper }) {
  return <article className="paper-card">{paper.coverUrl ? <img src={paper.coverUrl} alt="论文插图" loading="lazy" onError={(event) => { event.currentTarget.hidden = true; }} /> : null}<div><p className="eyebrow">{paper.year} · {paper.venue}</p><h2><Link to={`/dashboard/papers/${encodeURIComponent(paper.slug)}`}>{paper.title}</Link></h2>{paper.titleEn !== paper.title ? <p className="muted">{paper.titleEn}</p> : null}<p>{paper.authors}</p><p>{paper.tldr || paper.excerpt}</p><div className="tags">{paper.tags.map((tag) => <span key={tag}>{tag.replace(/^主题\//, '')}</span>)}</div></div></article>;
}
function PaperList() {
  const [query, setQuery] = useState(''); const deferred = useDeferredValue(query);
  const [params] = useSearchParams(); const domain = params.get('domain') || ''; const topic = getTopicDoc(params.get('topic') || '');
  const list = filterPapers(papers, deferred, { domain }).filter((paper) => !topic?.papers?.length || topic.papers.includes(paper.pid));
  return <><div className="workspace-heading"><h1>论文库</h1><Link className="button-link primary" to="/dashboard/import">添加论文</Link></div><label className="search-label">检索题名、作者、DOI、主题<input type="search" value={query} onChange={(event) => setQuery(event.target.value)} /></label><p className="muted">{list.length} 篇{domain ? ` · ${domain}` : ''} {topic ? ` · ${topic.title}` : ''}</p><div className="paper-list">{list.map((paper) => <PaperCard key={paper.slug} paper={paper} />)}</div>{!list.length ? <p>没有匹配的论文。</p> : null}</>;
}
function ReaderRoute() {
  const { slug = '' } = useParams(); const paper = getPaper(slug);
  return paper ? <PaperReader key={slug} paper={paper} /> : <p>论文不存在。<Link to="/dashboard/papers">返回论文库</Link></p>;
}
const readerTabs = [['article', '中文正文'], ['articleEn', '英文正文'], ['compare', '双语对照'], ['notes', 'AI 学习笔记'], ['cards', '概念卡'], ['images', '图库'], ['pdf', '原文 PDF']];
function PaperReader({ paper }: { paper: Paper }) {
  const [params, setParams] = useSearchParams(); const tab = params.get('tab') || 'article';
  const [data, setData] = useState(() => loadPaperData(paper.slug)); const [message, setMessage] = useState('');
  const [notesOpen, setNotesOpen] = useState(false); const [shareOpen, setShareOpen] = useState(false); const [vocabMode, setVocabMode] = useState(false); const [copyMode, setCopyMode] = useState(false);
  const [query, setQuery] = useState(''); const deferredQuery = useDeferredValue(query);
  const [headings, setHeadings] = useState<MarkdownHeading[]>([]);
  const article = useVaultText(tab === 'article' || tab === 'compare' ? paper.files.article : undefined);
  const english = useVaultText(tab === 'articleEn' || tab === 'compare' ? paper.files.articleEn || paper.files.txt : undefined);
  const analysis = useVaultText(tab === 'notes' ? paper.files.notes : tab === 'cards' ? paper.files.cards : undefined);
  const active = tab === 'article' || tab === 'compare' ? article : tab === 'articleEn' ? english : analysis;
  const onHeadings = useCallback((next: MarkdownHeading[]) => setHeadings(next), []);
  useReadingProgress({ slug: paper.slug, title: paper.title, tab: tab === 'compare' ? 'article' : tab, split: '', contentReady: Boolean(active.source), suspendSave: Boolean(query) });
  useEffect(() => { let alive = true; hydrateFromBackend(paper.slug).then((next) => { if (alive) setData(next); }); return () => { alive = false; }; }, [paper.slug]);
  const update = useCallback((patch: Partial<PaperUserData>) => {
    try { setData(savePaperData(paper.slug, patch)); } catch (error) { setMessage(errorText(error)); }
  }, [paper.slug]);
  const onHighlights = useCallback((highlights: PaperUserData['highlights']) => update({ highlights }), [update]);
  const onVocab = useCallback((vocab: PaperUserData['vocab']) => update({ vocab }), [update]);
  const clip = useCallback((text: string) => { update({ note: loadPaperData(paper.slug).note + `<blockquote>${escapeHtml(text)}</blockquote>` }); setNotesOpen(true); }, [paper.slug, update]);
  const onNote = useCallback((note: string) => update({ note }), [update]);
  const saveNow = async () => { try { await flushNotesBackend(paper.slug); setMessage('笔记与批注已保存'); } catch (error) { setMessage(errorText(error)); } };
  return <>
    <Link to="/dashboard/papers" className="muted">← 论文库</Link><h1>{paper.title}</h1><p className="muted">{paper.titleEn}</p><p>{paper.authors} · {paper.year} · {paper.venue}{paper.doi ? <> · <a href={`https://doi.org/${paper.doi}`} target="_blank" rel="noreferrer">DOI</a></> : null}</p>
    <div className="tabs" role="tablist" aria-label="论文内容">{readerTabs.map(([key, label]) => <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? 'selected' : ''} onClick={() => { setParams({ tab: key }); setHeadings([]); }}>{label}</button>)}</div>
    <div className="reader-tools"><input aria-label="查找正文" type="search" placeholder="查找正文…" value={query} onChange={(event) => setQuery(event.target.value)} /><label><input type="checkbox" checked={copyMode} onChange={(event) => setCopyMode(event.target.checked)} />公式源码</label><label><input type="checkbox" checked={vocabMode} onChange={(event) => setVocabMode(event.target.checked)} />双击标生词</label><button onClick={() => setNotesOpen(!notesOpen)}>我的笔记 {data.highlights.length ? `· ${data.highlights.length} 条高亮` : ''}</button><button onClick={() => downloadJson(`${paper.slug}.notes.json`, data)}>导出批注</button></div>
    <div className="reader-tools"><label>阅读状态<select value={data.flags.reading} onChange={(event) => update({ flags: { ...data.flags, reading: event.target.value as PaperUserData['flags']['reading'] } })}><option value="">未标记</option>{['在读', '已读', '重读'].map((value) => <option key={value}>{value}</option>)}</select></label><label>引用状态<select value={data.flags.cite} onChange={(event) => update({ flags: { ...data.flags, cite: event.target.value as PaperUserData['flags']['cite'] } })}><option value="">未标记</option><option>待引用</option><option>已引用</option></select></label><button aria-pressed={data.flags.starred} onClick={() => update({ flags: { ...data.flags, starred: !data.flags.starred } })}>{data.flags.starred ? '★ 重点论文' : '☆ 标为重点'}</button></div>
    <button onClick={() => setShareOpen(!shareOpen)}>{shareOpen ? '收起分享管理' : '单篇分享'}</button>
    {shareOpen ? <ShareManager paper={paper} /> : null}
    {message ? <p role="status" className="notice">{message}</p> : null}
    <div className={notesOpen ? 'reader-layout with-notes' : 'reader-layout'}>
      <article className="panel reader-content">
        {headings.length && tab !== 'compare' ? <details className="toc"><summary>目录</summary>{headings.map((heading) => <button key={heading.id} onClick={() => document.getElementById(heading.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>{heading.text}</button>)}</details> : null}
        {tab === 'images' ? <Gallery paper={paper} /> : tab === 'pdf' ? <PdfPane paper={paper} /> : tab === 'compare' ? <div className="bilingual"><div><h2>中文</h2><MarkdownNote source={article.source} empty={article.loading ? '正在读取…' : article.error || '没有中文正文'} pid={paper.pid} imagesDir={paper.files.imagesDir} highlightable tabKey="article" highlights={data.highlights} onHighlightsChange={onHighlights} onClip={clip} copyMode={copyMode} searchQuery={deferredQuery} /></div><div><h2>English</h2><MarkdownNote source={english.source} empty={english.loading ? 'Loading…' : english.error || 'No English text'} pid={paper.pid} imagesDir={paper.files.imagesDir} highlightable tabKey="articleEn" highlights={data.highlights} onHighlightsChange={onHighlights} onClip={clip} copyMode={copyMode} vocab={data.vocab} vocabMode={vocabMode} onVocabChange={onVocab} searchQuery={deferredQuery} /></div></div> : <MarkdownNote source={active.source} empty={active.loading ? '正在读取…' : active.error || '尚无此项内容'} pid={paper.pid} imagesDir={paper.files.imagesDir} highlightable tabKey={tab} highlights={data.highlights} onHighlightsChange={onHighlights} onClip={clip} vocab={tab === 'articleEn' ? data.vocab : undefined} vocabMode={vocabMode} onVocabChange={tab === 'articleEn' ? onVocab : undefined} copyMode={copyMode} onHeadings={onHeadings} searchQuery={deferredQuery} locateWord={params.get('word') || undefined} />}
      </article>
      {notesOpen ? <aside className="panel notes-panel"><h2>我的笔记</h2><NoteEditor value={data.note} onChange={onNote} /><button className="primary" onClick={() => void saveNow()}>保存笔记</button><h3>高亮</h3>{data.highlights.map((highlight) => <div className="annotation" key={highlight.id}><p>{highlight.text}</p><button onClick={() => onHighlights(data.highlights.filter((item) => item.id !== highlight.id))}>删除</button></div>)}<h3>本篇生词</h3>{data.vocab.map((word, index) => <p key={`${word.word}-${index}`}><strong>{word.word}</strong> — {word.context}</p>)}<button onClick={() => { const result = importPaperVocab({ slug: paper.slug, title: paper.title, entries: data.vocab }); setMessage(`已加入生词本：${result.added} 个新词`); }}>收入生词本</button><label className="file-label">导入本篇批注<input type="file" accept="application/json,.json" onChange={async (event) => { try { const file = event.target.files?.[0]; if (!file) return; const parsed = JSON.parse(await file.text()) as Partial<PaperUserData>; if (typeof parsed.note !== 'string' || !Array.isArray(parsed.highlights) || !Array.isArray(parsed.vocab)) throw new Error('批注文件格式不正确'); update({ note: DOMPurify.sanitize(parsed.note), highlights: parsed.highlights, vocab: parsed.vocab }); setMessage('已导入本篇批注'); } catch (error) { setMessage(errorText(error)); } finally { event.target.value = ''; } }} /></label></aside> : null}
    </div>
  </>;
}
function NoteEditor({ value, onChange }: { value: string; onChange: (html: string) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { if (ref.current && ref.current.innerHTML !== value) ref.current.innerHTML = DOMPurify.sanitize(value); }, [value]);
  return <><div className="editor-toolbar">{[['bold', '粗体'], ['italic', '斜体'], ['insertUnorderedList', '列表']].map(([command, title]) => <button key={command} onMouseDown={(event) => event.preventDefault()} onClick={() => { ref.current?.focus(); document.execCommand(command); if (ref.current) onChange(ref.current.innerHTML); }}>{title}</button>)}</div><div ref={ref} contentEditable suppressContentEditableWarning className="note-editor" role="textbox" aria-label="我的笔记正文" aria-multiline="true" onInput={() => { if (ref.current) onChange(DOMPurify.sanitize(ref.current.innerHTML)); }} onPaste={(event) => { event.preventDefault(); document.execCommand('insertText', false, event.clipboardData.getData('text/plain')); }} /></>;
}
function Gallery({ paper }: { paper: Paper }) {
  const [index, setIndex] = useState(-1); const images = paper.images || [];
  return <><div className="gallery">{images.map((image, i) => <button key={image.url} onClick={() => setIndex(i)}><img src={image.url} alt={image.caption || image.name} loading="lazy" /><span>{image.caption || image.name}</span></button>)}</div>{!images.length ? <p>没有单独整理的图片。</p> : null}<Lightbox open={index >= 0} close={() => setIndex(-1)} index={index} slides={images.map((image) => ({ src: image.url, title: image.caption || image.name }))} enableDownload /></>;
}
function PdfPane({ paper }: { paper: Paper }) {
  const [preview, setPreview] = useState(false);
  return paper.files.pdf ? <><div className="reader-tools"><button onClick={() => setPreview(true)}>预览原文 PDF</button><a href={paper.files.pdf} target="_blank" rel="noreferrer">新窗口打开</a><a href={paper.files.pdf} download>下载 PDF</a></div>{preview ? <iframe className="pdf-frame" title={`${paper.title} PDF`} src={paper.files.pdf} /> : <p className="muted">点击预览后加载原文。</p>}</> : <p>没有原文 PDF。</p>;
}
function TermsPage() {
  const [params] = useSearchParams(); const selected = getTerm(params.get('term') || ''); const [query, setQuery] = useState('');
  const deferred = useDeferredValue(query); const result = searchTerms(terms, deferred, {});
  return <><h1>术语库</h1><label className="search-label">搜索中英文术语<input type="search" value={query} onChange={(event) => setQuery(event.target.value)} /></label>{selected ? <article className="panel"><h2>{selected.term} · {selected.zhName}</h2><MarkdownNote source={selected.definition} empty="没有释义" /><p>{selected.fullName}</p><h3>论文中的用法</h3>{selected.usages.map((usage, index) => <p key={index}>{usage.paper}：{usage.context}</p>)}</article> : null}<div className="term-list">{result.filtered.slice(0, 120).map((term) => <article className="panel" key={term.key}><h2><Link to={`?term=${encodeURIComponent(term.key)}`}>{term.term}</Link></h2><p>{term.zhName}</p><p>{term.definition}</p><small>{term.type} · {term.domains.join(' / ')}</small></article>)}</div>{result.filtered.length > 120 ? <p>显示前 120 个匹配词，请继续搜索缩小范围。</p> : null}</>;
}
function TopicsPage() { return <><h1>方法与研究专题</h1>{topicDocs.length ? topicDocs.map((doc) => <article className="panel" key={doc.slug}><h2><Link to={`/dashboard/topics/${encodeURIComponent(doc.slug)}`}>{doc.title}</Link></h2><p>{doc.domain} · {doc.updatedAt}</p></article>) : <p>还没有专题。同步你整理的研究主题后，会显示在这里。</p>}</>; }
function TopicPage() {
  const { slug = '' } = useParams(); const topic = getTopicDoc(slug); const content = useVaultText(topic?.file);
  return topic ? <><Link to="/dashboard/topics">← 专题</Link><h1>{topic.title}</h1><article className="panel"><MarkdownNote source={content.source} empty={content.loading ? '正在读取…' : content.error || '没有内容'} /></article></> : <p>专题不存在。</p>;
}
function VocabPage() {
  const [book, setBook] = useState(loadVocabBook); const [query, setQuery] = useState(''); const [message, setMessage] = useState(''); const [busy, setBusy] = useState(false);
  useEffect(() => subscribeVocabBook(setBook), []);
  const filtered = book.filter((entry) => [entry.word, entry.en, entry.zh].join(' ').toLowerCase().includes(query.toLowerCase()));
  return <><h1>生词本</h1><div className="reader-tools"><input aria-label="搜索生词" type="search" value={query} onChange={(event) => setQuery(event.target.value)} /><button disabled={busy} onClick={async () => { setBusy(true); try { const result = await enrichVocabBook(); setMessage(result.error || `已补充 ${result.filled} 个词的释义`); } catch (error) { setMessage(errorText(error)); } finally { setBusy(false); } }}>{busy ? '正在补充…' : '用 AI 补充释义'}</button><button onClick={() => downloadJson('wenshu-vocabulary.json', book)}>导出生词本</button></div>{message ? <p role="status">{message}</p> : null}<p className="muted">在英文正文开启“双击标生词”，从“我的笔记”收入生词本。AI 接口由你在设置中配置。</p>{filtered.map((entry) => <VocabEditor key={entry.word} entry={entry} />)}{!filtered.length ? <p>生词本为空或没有匹配项。</p> : null}</>;
}
function VocabEditor({ entry }: { entry: VocabBookEntry }) {
  return <article className="panel vocab-entry"><h2>{entry.word} <small>{entry.ipa} {entry.pos}</small></h2><label>中文释义<textarea value={entry.zh} onChange={(event) => patchVocabEntry(entry.word, { zh: event.target.value })} /></label><label>英文释义<textarea value={entry.en} onChange={(event) => patchVocabEntry(entry.word, { en: event.target.value })} /></label>{entry.examples.map((example, index) => <p key={index}>{example.text} {example.slug ? <Link to={`/dashboard/papers/${encodeURIComponent(example.slug)}?tab=articleEn&word=${encodeURIComponent(entry.word)}`}>原句</Link> : null}</p>)}<button onClick={() => removeVocabWord(entry.word)}>删除词条</button></article>;
}
function SettingsPage() {
  const [ai, setAi] = useState(loadAiConfig); const [server, setServer] = useState(() => loadServerConfig().baseUrl); const [message, setMessage] = useState('');
  const [hover, setHover] = useState(loadHoverTips); const [termLinks, setTerms] = useState(loadTermLinks); const [dirs, setDirs] = useState({ notes: '', mirror: '' });
  const [email, setEmail] = useState(''); const [password, setPassword] = useState(''); const [busy, setBusy] = useState(false);
  useEffect(() => { if (isTauri()) Promise.all([getVaultDir(), getWebVaultDir()]).then(([notes, mirror]) => setDirs({ notes, mirror })).catch((error) => setMessage(errorText(error))); }, []);
  const run = async (task: () => Promise<unknown>, success: string) => { setBusy(true); try { await task(); setMessage(success); } catch (error) { setMessage(errorText(error)); } finally { setBusy(false); } };
  return <><h1>设置</h1>{message ? <p className="notice" role="status">{message}</p> : null}<section className="panel settings"><h2>阅读</h2><p>个人笔记、批注和阅读记录默认保存在本机，可在阅读页导出。</p><label><input type="checkbox" checked={hover} onChange={(event) => { setHover(event.target.checked); setHoverTips(event.target.checked); }} />引用与术语悬浮提示</label><label><input type="checkbox" checked={termLinks} onChange={(event) => { setTerms(event.target.checked); setTermLinks(event.target.checked); }} />正文术语链接</label></section>
    <section className="panel settings"><h2>AI 生词释义</h2><p>留空即可关闭。请求发送到你填写的兼容接口；Key 仅保存在本机浏览器数据中。</p><label>接口地址（含 /v1）<input value={ai.baseUrl} onChange={(event) => setAi({ ...ai, baseUrl: event.target.value })} placeholder="https://your-api.example/v1" /></label><label>API Key<input type="password" autoComplete="off" value={ai.apiKey} onChange={(event) => setAi({ ...ai, apiKey: event.target.value })} /></label><label>模型<input value={ai.model} onChange={(event) => setAi({ ...ai, model: event.target.value })} /></label><label>推理强度<select value={ai.reasoningEffort} onChange={(event) => setAi({ ...ai, reasoningEffort: event.target.value as typeof ai.reasoningEffort })}>{REASONING_EFFORT_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label><div className="reader-tools"><button onClick={() => { try { setAi(saveAiConfig(ai)); setMessage('AI 配置已保存'); } catch (error) { setMessage(errorText(error)); } }}>保存 AI 配置</button><button disabled={busy} onClick={() => void run(async () => { const ids = await fetchAiModels(ai); setMessage(ids.join(', ') || '接口未返回模型'); }, '模型列表已读取（可在接口返回后选择模型）')}>检查模型接口</button></div></section>
    {isTauri() ? <section className="panel settings"><h2>桌面文库</h2><p>笔记源文库：{dirs.notes || '应用默认目录'}</p><button disabled={busy} onClick={() => void run(async () => { const notes = await chooseVaultDir(); if (notes) setDirs((prev) => ({ ...prev, notes })); }, '笔记目录已设置')}>选择笔记源文库</button><p>阅读镜像：{dirs.mirror || '应用附带的示例库'}</p><button disabled={busy} onClick={() => void run(async () => { const mirror = await chooseWebVaultDir(); if (mirror) { setDirs((prev) => ({ ...prev, mirror })); await hydrateVaultData(); } }, '阅读镜像已更新')}>选择阅读镜像并刷新</button><button disabled={busy} onClick={() => void run(() => migrateLocalToVault(), '本机批注已写入笔记文库')}>将本机批注写入文库</button></section> : null}
    <section className="panel settings"><h2>可选账户与云同步</h2><p>填写你自行部署的服务地址；默认在本机使用。跨域部署须由服务器允许前端来源。</p><label>服务器地址<input value={server} onChange={(event) => setServer(event.target.value)} placeholder="https://your-server.example" /></label><button onClick={() => { try { saveServerConfig(server); setMessage('服务器地址已保存'); } catch (error) { setMessage(errorText(error)); } }}>保存服务器地址</button><label>邮箱<input type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} /></label><label>密码<input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} /></label><button disabled={busy} onClick={() => void run(async () => { if (!server.trim()) throw new Error('请先填写你部署的同步服务器地址'); saveServerConfig(server); const response = await client.post('/api/auth/sign-in', { email, password }); if (response.data.accessToken) client.defaults.headers.common.Authorization = `Bearer ${response.data.accessToken}`; setPassword(''); await initCloudSync(); }, '登录成功，已启用云同步')}>登录并同步</button><button disabled={busy} onClick={() => void run(async () => { await client.post('/api/auth/sign-out'); stopCloudSync(); delete client.defaults.headers.common.Authorization; await initTauriNotesBackend(); }, '已退出账户，恢复本机笔记保存')}>退出账户</button><p><Link to="/admin/users">管理服务器用户</Link></p></section>
  </>;
}

type ShareEntry = { token: string; slug: string; expiresAt: string | null; revoked: boolean };
function ShareManager({ paper }: { paper: Paper }) {
  const [shares, setShares] = useState<ShareEntry[]>([]); const [days, setDays] = useState('7'); const [message, setMessage] = useState(''); const [busy, setBusy] = useState(false);
  const serverConfigured = Boolean(loadServerConfig().baseUrl);
  useEffect(() => { if (!serverConfigured) return; let alive = true; client.get('/api/shares').then((response) => { if (alive) setShares((response.data.shares as ShareEntry[]).filter((item) => item.slug === paper.slug)); }).catch(() => { if (alive) setMessage('分享需要先在设置中登录自行部署的服务器。'); }); return () => { alive = false; }; }, [paper.slug, serverConfigured]);
  if (!serverConfigured) return <section className="panel"><h2>单篇分享</h2><p>连接自己的同步服务器后，可以创建论文分享链接。</p><Link to="/settings">配置同步服务器</Link></section>;
  const linkFor = (token: string) => `${window.location.origin}${appRouteUrl(`/share/${encodeURIComponent(token)}`)}`;
  return <section className="panel"><h2>单篇分享</h2><p className="muted">分享仅提供所选论文的阅读入口，不包含个人笔记与批注。公开网址需要部署前端；本机地址仅供本机查看。</p>{isTauri() ? <p>桌面端可管理分享令牌；公开阅读链接请使用你部署的 Web 前端网址加下方路径。</p> : null}<div className="reader-tools"><select aria-label="分享有效期" value={days} onChange={(event) => setDays(event.target.value)}><option value="7">7 天</option><option value="30">30 天</option><option value="0">长期有效</option></select><button disabled={busy} onClick={async () => { setBusy(true); try { const response = await client.post('/api/shares', { slug: paper.slug, days: Number(days) || null }); setShares((previous) => [response.data.share, ...previous]); setMessage('分享令牌已创建'); } catch (error) { setMessage(errorText(error)); } finally { setBusy(false); } }}>创建分享</button></div>{message ? <p role="status">{message}</p> : null}{shares.map((share) => <div key={share.token} className="reader-tools"><input aria-label="分享地址" readOnly value={isTauri() ? `/share/${share.token}` : linkFor(share.token)} /><small>{share.expiresAt || '长期有效'}</small><button onClick={async () => setMessage(await copyText(isTauri() ? `/share/${share.token}` : linkFor(share.token)) ? '已复制' : '请手动复制地址')}>复制</button><button onClick={async () => { try { await client.delete(`/api/shares/${encodeURIComponent(share.token)}`); setShares((previous) => previous.filter((item) => item.token !== share.token)); setMessage('分享已撤销'); } catch (error) { setMessage(errorText(error)); } }}>撤销</button></div>)}</section>;
}
function SharedPaperPage() {
  const { token = '' } = useParams(); const [paper, setPaper] = useState<Paper | null>(null); const [error, setError] = useState(''); const [tab, setTab] = useState('article');
  useEffect(() => { let alive = true; client.get(`/api/share/${encodeURIComponent(token)}/meta`).then((response) => { if (alive) setPaper(response.data.paper); }).catch(() => { if (alive) setError('分享链接不存在、已失效，或服务器尚未配置。'); }); return () => { alive = false; }; }, [token]);
  const source = useVaultText(tab === 'pdf' ? undefined : paper?.files[tab as 'article' | 'articleEn']);
  if (error) return <p role="alert">{error}</p>;
  if (!paper) return <p role="status">正在读取分享…</p>;
  return <><h1>{paper.title}</h1><p>{paper.authors} · {paper.year} · {paper.venue}</p><div className="tabs">{[['article', '中文正文'], ['articleEn', '英文正文'], ['pdf', '原文 PDF']].map(([key, title]) => <button key={key} onClick={() => setTab(key)} className={tab === key ? 'selected' : ''}>{title}</button>)}</div><article className="panel">{tab === 'pdf' ? <PdfPane paper={paper} /> : <MarkdownNote source={source.source} empty={source.loading ? '正在读取…' : source.error || '没有此项内容'} pid={paper.pid} imagesDir={paper.files.imagesDir} shareMode />}</article></>;
}
type UserRecord = { id: string; email: string; displayName: string; role: 'admin' | 'reader'; disabled: boolean };
function AdminPage() {
  const [users, setUsers] = useState<UserRecord[]>([]); const [message, setMessage] = useState(''); const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ email: '', password: '', displayName: '', role: 'reader' });
  const reload = useCallback(async () => { const response = await client.get('/api/users'); setUsers(response.data.users || []); }, []);
  const serverConfigured = Boolean(loadServerConfig().baseUrl);
  useEffect(() => { if (!serverConfigured) return; reload().catch(() => setMessage('请先在设置中登录管理员账户；服务器会验证管理权限。')); }, [reload, serverConfigured]);
  if (!serverConfigured) return <><h1>用户管理</h1><p>请先连接自己的同步服务器。</p><Link to="/settings">配置同步服务器</Link></>;
  const patch = async (user: UserRecord, value: Partial<UserRecord>) => { setBusy(true); try { await client.patch(`/api/users/${user.id}`, value); await reload(); setMessage('用户信息已更新'); } catch (error) { setMessage(errorText(error)); } finally { setBusy(false); } };
  return <><h1>用户管理</h1>{message ? <p role="status" className="notice">{message}</p> : null}<section className="panel settings"><h2>添加用户</h2><label>邮箱<input type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} /></label><label>显示名称<input value={form.displayName} onChange={(event) => setForm({ ...form, displayName: event.target.value })} /></label><label>初始密码<input type="password" autoComplete="new-password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} /></label><label>角色<select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}><option value="reader">reader</option><option value="admin">admin</option></select></label><button disabled={busy} onClick={async () => { setBusy(true); try { await client.post('/api/users', form); setForm({ email: '', password: '', displayName: '', role: 'reader' }); await reload(); setMessage('用户已创建'); } catch (error) { setMessage(errorText(error)); } finally { setBusy(false); } }}>创建用户</button></section>{users.map((user) => <article className="panel" key={user.id}><h2>{user.displayName || user.email}</h2><p>{user.email} · {user.disabled ? '已停用' : '启用中'}</p><div className="reader-tools"><select aria-label={`${user.email} 的角色`} value={user.role} disabled={busy} onChange={(event) => void patch(user, { role: event.target.value as UserRecord['role'] })}><option value="reader">reader</option><option value="admin">admin</option></select><button disabled={busy} onClick={() => void patch(user, { disabled: !user.disabled })}>{user.disabled ? '启用' : '停用'}</button></div></article>)}</>;
}
