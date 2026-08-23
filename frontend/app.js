// The chat page. Chats, documents, messages, and the admin panel.

import { api, token, requireToken } from "./api.js";

requireToken();

const POLL_MS = 2000;

const state = {
  me: null,
  chats: [],
  openId: null,
  // A chat the user started but has not sent anything to yet. It has no
  // row in Postgres until the first message or the first upload, so
  // clicking New chat repeatedly cannot litter the database.
  draft: false,
  documents: [],
  poll: null,
  busy: false,
};

const $ = (id) => document.getElementById(id);

// Text from the API is never written as HTML.
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// ---------------------------------------------------------------
// Who is logged in
// ---------------------------------------------------------------

async function loadMe() {
  state.me = await api.get("/auth/me");
  $("whoami").textContent = state.me.email;
  $("openAdmin").hidden = state.me.role !== "admin";
}

$("logout").onclick = (event) => {
  event.preventDefault();
  token.clear();
  location.href = "login.html";
};

// ---------------------------------------------------------------
// Chats
// ---------------------------------------------------------------

function chatTitle(chat) {
  return chat.title || "Untitled";
}

async function loadChats() {
  state.chats = await api.get("/threads");
  drawChats();
}

function drawChats() {
  const list = $("chats");
  list.replaceChildren();

  if (state.draft) {
    const row = el("div", "chat on");
    row.append(el("span", null, "New chat"));
    list.append(row);
  }

  if (!state.chats.length && !state.draft) {
    list.append(el("div", "railempty", "No chats yet. Start one above."));
    return;
  }

  for (const chat of state.chats) {
    const row = el("div", "chat" + (chat.thread_id === state.openId ? " on" : ""));
    row.append(el("span", null, chatTitle(chat)));

    const kill = el("button", "kill", "✕");
    kill.title = "Delete this chat";
    kill.onclick = (event) => {
      event.stopPropagation();
      removeChat(chat);
    };
    row.append(kill);

    row.onclick = () => openChat(chat.thread_id);
    list.append(row);
  }
}

$("newChat").onclick = () => {
  state.draft = true;
  state.openId = null;
  state.documents = [];
  stopPolling();
  drawChats();
  drawFiles();
  setHeader();
  $("thread").replaceChildren(emptyState(
    "A new chat",
    "Add a PDF on the right, then ask about it. The chat is created when you " +
    "send your first message."
  ));
  $("message").focus();
};

async function removeChat(chat) {
  if (!confirm(`Delete "${chatTitle(chat)}"? Its documents go with it.`)) return;
  await api.delete(`/threads/${chat.thread_id}`);
  if (state.openId === chat.thread_id) {
    state.openId = null;
    stopPolling();
  }
  await loadChats();
  await openFirstOrEmpty();
}

async function openChat(threadId) {
  state.openId = threadId;
  state.draft = false;
  drawChats();
  setHeader();

  $("thread").replaceChildren(emptyState("Loading…", ""));
  await Promise.all([loadMessages(), loadDocuments()]);
}

async function openFirstOrEmpty() {
  if (state.chats.length) return openChat(state.chats[0].thread_id);

  state.openId = null;
  state.documents = [];
  drawFiles();
  setHeader();
  $("thread").replaceChildren(emptyState(
    "Nothing here yet",
    "Start a chat, add a PDF, and ask about it."
  ));
}

// Created on the first real action, titled from whatever caused it.
async function ensureChat(title) {
  if (state.openId) return state.openId;

  const chat = await api.post("/threads", { title: title.slice(0, 60) });
  state.chats.unshift(chat);
  state.openId = chat.thread_id;
  state.draft = false;
  drawChats();
  setHeader();
  return chat.thread_id;
}

// ---------------------------------------------------------------
// Header
// ---------------------------------------------------------------

function setHeader() {
  const ready = state.documents.filter((d) => d.status === "ready");
  const working = state.documents.filter(
    (d) => d.status === "pending" || d.status === "processing"
  );

  let text = "No chat open";
  if (state.draft) text = "New chat · no documents yet";
  else if (state.openId) {
    const chat = state.chats.find((c) => c.thread_id === state.openId);
    const parts = [chat ? chatTitle(chat) : "Chat"];
    if (!state.documents.length) parts.push("no documents yet");
    else {
      parts.push(`${ready.length} document${ready.length === 1 ? "" : "s"} ready`);
      if (working.length) parts.push(`${working.length} still reading`);
    }
    text = parts.join(" · ");
  }

  $("chatState").textContent = text;
  $("live").className = "live" + (ready.length ? "" : " idle");

  const chunks = ready.reduce((total, d) => total + (d.chunk_count || 0), 0);
  $("chunkCount").textContent = chunks ? `${chunks} chunks` : "";
}

function emptyState(heading, body) {
  const box = el("div", "empty");
  box.append(el("h3", null, heading));
  if (body) box.append(el("p", null, body));
  return box;
}

// ---------------------------------------------------------------
// Documents
// ---------------------------------------------------------------

const STATUS_TEXT = {
  pending: "queued",
  processing: "reading document",
  ready: null,
  failed: null,
};

async function loadDocuments() {
  if (!state.openId) {
    state.documents = [];
    drawFiles();
    return;
  }
  state.documents = await api.get(`/threads/${state.openId}/documents`);
  drawFiles();
  setHeader();
  schedulePoll();
}

function drawFiles() {
  const list = $("fileList");
  list.replaceChildren();
  $("addFile").disabled = false;

  if (!state.documents.length) {
    list.append(el("div", "filesempty",
      state.openId || state.draft
        ? "No PDFs in this chat yet."
        : "Open a chat to add PDFs."));
    $("addFile").disabled = !state.openId && !state.draft;
    return;
  }

  for (const doc of state.documents) {
    const card = el("div", "file");

    const row = el("div", "row");
    const dot = el("span", "dot " +
      (doc.status === "ready" ? "ready" : doc.status === "failed" ? "fail" : "work"));
    row.append(dot, el("span", "n", doc.filename));

    const kill = el("button", "kill", "✕");
    kill.title = "Remove this document";
    kill.onclick = () => removeDocument(doc);
    row.append(kill);
    card.append(row);

    if (doc.status === "ready") {
      const pages = doc.page_count ? ` · ${doc.page_count} pages` : "";
      card.append(el("div", "s", `${doc.chunk_count} chunks${pages}`));
    } else if (doc.status === "failed") {
      // The worker's message says what to do about it, so show it as-is.
      card.append(el("div", "s bad", doc.error_message || "Could not read this PDF"));
    } else {
      card.append(el("div", "s", STATUS_TEXT[doc.status] || doc.status));
    }

    list.append(card);
  }
}

async function removeDocument(doc) {
  if (!confirm(`Remove ${doc.filename} from this chat?`)) return;
  await api.delete(`/threads/${state.openId}/documents/${doc.document_id}`);
  await loadDocuments();
}

$("addFile").onclick = () => $("picker").click();

$("picker").onchange = async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  event.target.value = "";

  try {
    // Uploading into a new chat is a real action, so the chat is
    // created here and named after the file.
    const threadId = await ensureChat(file.name.replace(/\.pdf$/i, ""));
    await api.upload(`/threads/${threadId}/documents`, file);
    await loadDocuments();
  } catch (err) {
    alert(err.message);
  }
};

// Poll only while something is still being read. Upload never blocks,
// so this is the only way the rail learns the document is ready.
function schedulePoll() {
  stopPolling();
  const working = state.documents.some(
    (d) => d.status === "pending" || d.status === "processing"
  );
  if (!working) return;

  state.poll = setTimeout(async () => {
    const openWhenScheduled = state.openId;
    try {
      const fresh = await api.get(`/threads/${openWhenScheduled}/documents`);
      // The user may have switched chats while this was in flight.
      if (state.openId !== openWhenScheduled) return;
      state.documents = fresh;
      drawFiles();
      setHeader();
      schedulePoll();
    } catch {
      // A poll failing is not worth interrupting anyone over.
    }
  }, POLL_MS);
}

function stopPolling() {
  if (state.poll) clearTimeout(state.poll);
  state.poll = null;
}

// ---------------------------------------------------------------
// Messages
// ---------------------------------------------------------------

async function loadMessages() {
  const thread = $("thread");
  const history = await api.get(`/threads/${state.openId}/messages`);
  thread.replaceChildren();

  if (!history.length) {
    thread.append(emptyState(
      "Ask about your documents",
      "Every answer comes from the PDFs in this chat and shows the page it " +
      "was read from."
    ));
    return;
  }

  for (const message of history) {
    thread.append(
      message.role === "user"
        ? drawAsk(message.content)
        : drawSay(message.content, message.sources)
    );
  }
  scrollDown();
}

function drawAsk(text) {
  return el("div", "ask", text);
}

function drawSay(text, sources) {
  const box = el("div", "say");
  for (const paragraph of String(text).split(/\n{2,}/)) {
    box.append(el("p", null, paragraph.trim()));
  }
  // No sources means it did not come from the documents, which is
  // correct for small talk and for a refusal.
  if (sources && sources.length) box.append(drawCites(sources));
  return box;
}

function drawCites(sources) {
  const row = el("div", "cites");
  for (const source of sources) {
    const wrap = el("span", "ev");
    wrap.append(el("span", "cite", `p.${source.page}`));

    const pop = el("span", "pop");
    pop.append(el("span", "src", `${source.filename} · page ${source.page}`));
    pop.append(el("span", "txt", source.text));
    wrap.append(pop);

    row.append(wrap);
  }
  return row;
}

function scrollDown() {
  const stream = $("stream");
  stream.scrollTop = stream.scrollHeight;
}

async function sendMessage() {
  const input = $("message");
  const text = input.value.trim();
  if (!text || state.busy) return;

  state.busy = true;
  $("send").disabled = true;
  input.value = "";

  const thread = $("thread");
  if (thread.querySelector(".empty")) thread.replaceChildren();
  thread.append(drawAsk(text));

  const waiting = el("div", "working");
  waiting.append(el("span", null, "Searching documents"), el("i"));
  thread.append(waiting);
  scrollDown();

  try {
    const threadId = await ensureChat(text);
    const reply = await api.post(`/threads/${threadId}/chat`, { message: text });
    waiting.replaceWith(drawSay(reply.answer, reply.sources));

    // The chat may have just been created, and its ordering changes
    // with every message.
    await loadChats();
    if (!state.documents.length) await loadDocuments();
  } catch (err) {
    waiting.replaceWith(el("div", "oops", err.message));
  } finally {
    state.busy = false;
    $("send").disabled = false;
    scrollDown();
    input.focus();
  }
}

$("send").onclick = sendMessage;
$("message").onkeydown = (event) => {
  if (event.key === "Enter") sendMessage();
};

// ---------------------------------------------------------------
// Admin panel
// ---------------------------------------------------------------

const scrim = $("scrim");
const closePanel = () => scrim.classList.remove("open");

$("openAdmin").onclick = async () => {
  scrim.classList.add("open");
  $("panelError").textContent = "";
  await loadUsers();
};
$("closeAdmin").onclick = closePanel;
scrim.onclick = (event) => { if (event.target === scrim) closePanel(); };
addEventListener("keydown", (event) => { if (event.key === "Escape") closePanel(); });

function shortDate(value) {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("en-GB",
    { day: "numeric", month: "short", year: "numeric" });
}

async function loadUsers() {
  const people = await api.get("/users");
  const body = $("people");
  body.replaceChildren();

  for (const person of people) {
    const row = el("tr");
    row.append(el("td", "mono", person.email));

    const roleCell = el("td");
    roleCell.append(el("span",
      "role" + (person.role === "admin" ? " admin" : ""), person.role));
    row.append(roleCell);

    row.append(el("td", "dim", person.added_by_email || "—"));
    row.append(el("td", "dim", shortDate(person.created_at)));

    const actions = el("td");
    const isMe = person.user_id === state.me.user_id;
    const kill = el("button", "remove", isMe ? "you" : "Remove");
    kill.disabled = isMe;
    if (!isMe) kill.onclick = () => removeUser(person);
    actions.append(kill);
    row.append(actions);

    body.append(row);
  }

  $("teamSub").textContent =
    `${state.me.tenant_name} · ${people.length} ${people.length === 1 ? "person" : "people"}`;
  $("userCount").textContent = people.length;
}

async function removeUser(person) {
  if (!confirm(
    `Remove ${person.email}? Their chats, documents and messages go with them.`
  )) return;

  try {
    await api.delete(`/users/${person.user_id}`);
    await loadUsers();
  } catch (err) {
    $("panelError").textContent = err.message;
  }
}

$("addUser").onclick = async () => {
  const email = $("newEmail");
  const password = $("newPw");
  $("panelError").textContent = "";

  if (!email.value.trim() || !password.value) {
    $("panelError").textContent = "Enter an email and a temporary password";
    return;
  }

  try {
    await api.post("/users", {
      email: email.value.trim(),
      password: password.value,
      role: $("newRole").value,
    });
    email.value = password.value = "";
    await loadUsers();
  } catch (err) {
    $("panelError").textContent = err.message;
  }
};

// ---------------------------------------------------------------
// Start
// ---------------------------------------------------------------

(async () => {
  try {
    await loadMe();
    await loadChats();
    if (state.me.role === "admin") await loadUsers();
    await openFirstOrEmpty();
  } catch (err) {
    $("thread").replaceChildren(emptyState("Could not load", err.message));
  }
})();
