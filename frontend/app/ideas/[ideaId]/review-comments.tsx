"use client";

import { CornerDownRight, MessageSquareText, Send } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { SectionCard, StatusPill } from "@/components/ui/workspace";
import { apiRequest } from "@/lib/api";
import styles from "./review-comments.module.css";

type Comment = { id: string; parent_id: string | null; round_number: number; author_name: string; author_role: "approver" | "submitter" | "consulted" | "admin"; body: string; created_at: string; is_mine: boolean };
export type CommentThread = { comments: Comment[]; can_comment: boolean; consulted_on: string[]; unanswered_for_me: number };

const roleLabel: Record<Comment["author_role"], string> = { approver: "Approver", submitter: "Submitter", consulted: "Consulted", admin: "Workspace Admin" };
const stamp = new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });

/** Review comments while an idea is in approval: advice from consulted colleagues and replies. */
export function ReviewComments({ ideaId, refreshKey, onThread }: { ideaId: string; refreshKey: number; onThread?: (thread: CommentThread | null) => void }) {
  const [thread, setThread] = useState<CommentThread | null>(null);
  const [hidden, setHidden] = useState(false);
  const [draft, setDraft] = useState("");
  const [replyTo, setReplyTo] = useState<string | null>(null);
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const response = await apiRequest(`/ideas/${ideaId}/comments`).catch(() => null);
    if (!response) return;
    if (response.status === 403 || response.status === 404) { setHidden(true); onThread?.(null); return; }
    if (response.ok) { const next = await response.json() as CommentThread; setThread(next); onThread?.(next); }
  }, [ideaId, onThread]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load, refreshKey]);

  const send = async (body: string, parentId: string | null) => {
    setBusy(true); setError("");
    try {
      const response = await apiRequest(`/ideas/${ideaId}/comments`, { method: "POST", body: JSON.stringify({ body, parent_id: parentId }) });
      if (!response.ok) { const payload = await response.json().catch(() => null) as { detail?: string } | null; setError(typeof payload?.detail === "string" ? payload.detail : "The comment could not be posted."); return; }
      const next = await response.json() as CommentThread;
      setThread(next); onThread?.(next);
      if (parentId) { setReply(""); setReplyTo(null); } else setDraft("");
    } catch {
      setError("Comments are temporarily unavailable.");
    } finally { setBusy(false); }
  };

  if (hidden || !thread) return null;
  const topLevel = thread.comments.filter((comment) => !comment.parent_id);
  const replies = (id: string) => thread.comments.filter((comment) => comment.parent_id === id);

  return <SectionCard
    icon={<MessageSquareText size={17} />}
    title="Review comments"
    description={thread.consulted_on.length ? `You were asked for your view at: ${thread.consulted_on.join(", ")}. Your comments don't block the decision; the approver sees them and can reply.` : "Advice from colleagues asked to comment, and replies from the approver and submitter."}
    meta={thread.unanswered_for_me ? `${thread.unanswered_for_me} awaiting your reply` : `${topLevel.length} comment${topLevel.length === 1 ? "" : "s"}`}
  >
    {error ? <p className={styles.error} role="alert">{error}</p> : null}
    {topLevel.length ? <ol className={styles.thread}>{topLevel.map((comment) => <li key={comment.id}>
      <CommentBody comment={comment} />
      {replies(comment.id).length ? <ol className={styles.replies}>{replies(comment.id).map((child) => <li key={child.id}><CommentBody comment={child} /></li>)}</ol> : null}
      {thread.can_comment ? replyTo === comment.id
        ? <form className={styles.replyForm} onSubmit={(event: FormEvent) => { event.preventDefault(); if (reply.trim()) void send(reply.trim(), comment.id); }}>
            <label className={styles.srOnly} htmlFor={`reply-${comment.id}`}>Reply to {comment.author_name}</label>
            <textarea id={`reply-${comment.id}`} value={reply} maxLength={4000} rows={2} onChange={(event) => setReply(event.target.value)} placeholder={`Reply to ${comment.author_name}`} autoFocus />
            <div className={styles.formActions}><button type="button" className={styles.ghost} onClick={() => { setReplyTo(null); setReply(""); }}>Cancel</button><button type="submit" className={styles.send} disabled={busy || !reply.trim()}><Send size={14} aria-hidden="true" />Reply</button></div>
          </form>
        : <button type="button" className={styles.replyButton} onClick={() => { setReplyTo(comment.id); setReply(""); }}><CornerDownRight size={14} aria-hidden="true" />Reply</button>
        : null}
    </li>)}</ol> : <p className={styles.empty}>No comments yet.</p>}
    {thread.can_comment ? <form className={styles.compose} onSubmit={(event: FormEvent) => { event.preventDefault(); if (draft.trim()) void send(draft.trim(), null); }}>
      <label htmlFor="new-review-comment">Add a comment</label>
      <textarea id="new-review-comment" value={draft} maxLength={4000} rows={3} onChange={(event) => setDraft(event.target.value)} placeholder="Practical concerns, similar work elsewhere, risks the approver should weigh…" />
      <div className={styles.formActions}><span>{draft.length}/4000</span><button type="submit" className={styles.send} disabled={busy || !draft.trim()}><Send size={14} aria-hidden="true" />{busy ? "Posting" : "Post comment"}</button></div>
    </form> : null}
  </SectionCard>;
}

function CommentBody({ comment }: { comment: Comment }) {
  return <article className={styles.comment} data-mine={comment.is_mine}>
    <header><strong>{comment.author_name}</strong><StatusPill tone={comment.author_role === "approver" ? "info" : comment.author_role === "consulted" ? "warning" : "neutral"}>{roleLabel[comment.author_role]}</StatusPill><time dateTime={comment.created_at}>{stamp.format(new Date(comment.created_at))}</time>{comment.round_number > 1 ? <span className={styles.round}>Round {comment.round_number}</span> : null}</header>
    <p>{comment.body}</p>
  </article>;
}
