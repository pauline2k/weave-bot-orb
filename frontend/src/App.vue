<template>
  <main class="wrap">
    <header class="header">
      <h1>🔮 Oakland Review of Books calendar of (not just) literary events</h1>
    </header>

    <section class="panel loginPanel" v-if="!isLoggedIn">
      <h2 class="h2">Login</h2>

      <form class="form" @submit.prevent="submitLogin">
        <label class="field">
          <span class="fieldLabel">Username</span>
          <input class="input" v-model="loginUser" required />
        </label>

        <label class="field">
          <span class="fieldLabel">Password</span>
          <input class="input" type="password" v-model="loginPass" required />
        </label>

        <div class="formActions">
          <button class="btn" :disabled="loggingIn">
            {{ loggingIn ? "Signing in…" : "Login" }}
          </button>
          <span v-if="loginError" class="errorInline">{{ loginError }}</span>
        </div>
      </form>
    </section>

    <section class="controls" v-if="isLoggedIn">
      <label class="label">
        <span>Week of:</span>
        <select class="select" v-model="selectedMonday">
          <option v-for="d in mondayOptions" :key="d" :value="d">
            {{ d }}
          </option>
        </select>
      </label>
      <button class="btn" :disabled="loading" @click="fetchCalendar">
        {{ loading ? "Loading…" : "Reload" }}
      </button>
      <span v-if="lastUpdated" class="meta">Last updated: {{ lastUpdated }}</span>
      <label class="checkboxLabel">
        <input type="checkbox" v-model="allowEdits" />
        <span>Allow edits</span>
      </label>
    </section>

    <section v-if="error" class="error">
      <strong>Error:</strong> {{ error }}
    </section>

    <section class="panel" v-if="isLoggedIn">
      <div v-if="Object.keys(groupedByDateAndSupplemental).length === 0" class="empty">
        No data yet.
      </div>
      <div v-for="(events, date) in groupedByDateAndSupplemental" :key="date" class="day">
        <p>
          <strong><u>{{ formatDisplayDate(date) }}</u></strong>
        </p>
        <div v-for="event in events['false']">
          <p
            :class="{'text-not-done': !event.calendar_metadata?.done, 'text-done': event.calendar_metadata?.done}"
            v-if="event.grist_record_id !== currentEditEventId"
          >
            <strong>
              {{event.title}}
            </strong>,
            {{ formatTime12h(event.start_datetime) }},
            {{ event.location?.venue }}
            ({{ event.location?.neighborhood || event.location?.city || 'Oakland'}}).
            <span v-html="itemDescriptionHtml(event.description || '')"></span>
            [<a :href="event.source_url">{{event.source_url_provider || event.organizer?.name || event.source_url}}</a>]
            <button
              v-if="allowEdits && !currentEditEventId"
              class="btn btn-edit-full"
              type="button"
              @click="setCurrentEditEvent(event)"
            >
              Edit event
            </button>
          </p>
          <section class="panel formPanel" v-if="event.grist_record_id === currentEditEventId">
            <form class="form" @submit.prevent="submitEditedItem">
              <label class="field">
                <span class="fieldLabel">Title</span>
                <input class="input" type="text" v-model="editedItemTitle" />
              </label>

              <label class="field">
                <span class="fieldLabel">Date/Time</span>
                <input
                  class="input"
                  type="datetime-local"
                  v-model="editedItemStartDatetime"
                  required
                />
              </label>

              <label class="field">
                <span class="fieldLabel">Venue</span>
                <input class="input" type="text" v-model="editedItemVenue" />
              </label>

              <label class="field">
                <span class="fieldLabel">City/Neighborhood</span>
                <input class="input" type="text" v-model="editedItemNeighborhood" />
              </label>

              <label class="field">
                <span class="fieldLabel">Description</span>
              </label>
              <div class="mdWrap">
                <div class="mdToolbar">
                  <button class="btn" type="button"
                    :disabled="!descriptionEditor"
                    @mousedown.prevent.stop
                    @click="descriptionEditor?.chain().focus().toggleBold().run()"
                  >
                    Bold
                  </button>

                  <button class="btn" type="button"
                    :disabled="!descriptionEditor"
                    @mousedown.prevent
                    @click="descriptionEditor?.chain().focus().toggleItalic().run()"
                  >
                    Italic
                  </button>

                  <button class="btn" type="button"
                    :disabled="!descriptionEditor"
                    @mousedown.prevent
                    @click="setLink"
                  >
                    Link
                  </button>
                </div>

                <EditorContent :editor="descriptionEditor" />
              </div>

              <label class="field">
                <span class="fieldLabel">URL</span>
                <input class="input" type="text" v-model="editedItemSourceUrl" />
              </label>

              <label class="field">
                <span class="fieldLabel">URL Provider</span>
                <input class="input" type="text" v-model="editedItemSourceUrlProvider" />
              </label>

              <label class="checkboxLabel">
                <input type="checkbox" v-model="editedItemMetadataSupplemental" />
                <span>Mark as "Also"</span>
              </label>

              <label class="checkboxLabel">
                <input type="checkbox" v-model="editedItemMetadataDone" />
                <span>Mark as done</span>
              </label>

              <div class="formActions">
                <button class="btn" type="submit" :disabled="updating">
                  {{ updating ? "Saving…" : "Update" }}
                </button>
                <button class="btn" type="button" :disabled="updating" @click="onCancelUpdate">
                  Cancel
                </button>

                <span v-if="updateOk" class="ok">Updated.</span>
                <span v-if="updateError" class="errorInline">Error: {{ updateError }}</span>
              </div>
            </form>
          </section>
        </div>

        <div v-if="events['true']?.length">
          <strong>Also: </strong>
          <span
            v-for="(event, index) in events['true']"
            :class="{'text-not-done': !event.calendar_metadata?.done, 'text-done': event.calendar_metadata?.done}"
          >
            <a :href="event.source_url">{{ event.title }}</a> at {{ event.location?.venue }} ({{ event.location?.neighborhood }})
            <button
              v-if="allowEdits && !currentEditEventId"
              type="button"
              class="btn btn-inline"
              @click="setCurrentEditEvent(event)"
            >
              Edit event
            </button>
            <span v-if="index !== events['true'].length - 1">/ </span>
            <section class="panel formPanel" v-if="event.grist_record_id === currentEditEventId">
              <form class="form" @submit.prevent="submitEditedItem">
                <label class="field">
                  <span class="fieldLabel">Title</span>
                  <input class="input" type="text" v-model="editedItemTitle" />
                </label>

                <label class="field">
                  <span class="fieldLabel">Date/Time</span>
                  <input
                    class="input"
                    type="datetime-local"
                    v-model="editedItemStartDatetime"
                    required
                  />
                </label>

                <label class="field">
                  <span class="fieldLabel">Venue</span>
                  <input class="input" type="text" v-model="editedItemVenue" />
                </label>

                <label class="field">
                  <span class="fieldLabel">City/Neighborhood</span>
                  <input class="input" type="text" v-model="editedItemNeighborhood" />
                </label>

                <span class="fieldLabel">Description</span>
                <div class="mdWrap">
                  <div class="mdToolbar">
                    <button class="btn" type="button"
                      :disabled="!descriptionEditor"
                      @mousedown.prevent
                      @click="descriptionEditor?.chain().focus().toggleBold().run()"
                    >
                      Bold
                    </button>

                    <button class="btn" type="button"
                      :disabled="!descriptionEditor"
                      @mousedown.prevent
                      @click="descriptionEditor?.chain().focus().toggleItalic().run()"
                    >
                      Italic
                    </button>

                    <button class="btn" type="button"
                      :disabled="!descriptionEditor"
                      @mousedown.prevent
                      @click="setLink"
                    >
                      Link
                    </button>
                  </div>

                  <EditorContent :editor="descriptionEditor" />
                </div>

                <label class="field">
                  <span class="fieldLabel">URL</span>
                  <input class="input" type="text" v-model="editedItemSourceUrl" />
                </label>

                <label class="field">
                  <span class="fieldLabel">URL Provider</span>
                  <input class="input" type="text" v-model="editedItemSourceUrlProvider" />
                </label>

                <label class="checkboxLabel">
                  <input type="checkbox" v-model="editedItemMetadataSupplemental" />
                  <span>Mark as "Also"</span>
                </label>

                <label class="checkboxLabel">
                  <input type="checkbox" v-model="editedItemMetadataDone" />
                  <span>Mark as done</span>
                </label>

                <div class="formActions">
                  <button class="btn" type="submit" :disabled="updating">
                    {{ updating ? "Saving…" : "Update" }}
                  </button>
                  <button class="btn" type="button" :disabled="updating" @click="onCancelUpdate">
                    Cancel
                  </button>

                  <span v-if="updateOk" class="ok">Updated.</span>
                  <span v-if="updateError" class="errorInline">Error: {{ updateError }}</span>
                </div>
              </form>
            </section>
          </span>
        </div>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useEditor, EditorContent } from "@tiptap/vue-3";
import StarterKit from "@tiptap/starter-kit";
import Link from "@tiptap/extension-link";
import { Markdown } from "@tiptap/markdown";
import MarkdownIt from "markdown-it";
import DOMPurify from "dompurify";

type CalendarLocation = {
  city?: string | null,
  venue?: string | null,
  neighborhood?: string | null,
  [key: string]: unknown
}

type CalendarMetadata = {
  deleted?: boolean,
  done?: boolean,
  incoming?: boolean,
  supplemental?: boolean
}

type CalendarOrganizer = {
  name?: string,
}

type CalendarEvent = {
  start_datetime: string // ISO 8601 datetime,
  grist_record_id?: number,
  description?: string | null,
  title: string | null,
  source_url?: string,
  source_url_provider?: string | null,
  location?: CalendarLocation,
  organizer?: CalendarOrganizer,
  calendar_metadata?: CalendarMetadata,
  // Other properties exist but are not relevant here.
  [key: string]: unknown
}

const loginUser = ref("");
const loginPass = ref("");
const loginError = ref("");
const loggingIn = ref(false);
const isLoggedIn = ref(false);

const loading = ref<boolean>(false)
const allowEdits = ref<boolean>(false)
const error = ref<string>('')
const payload = ref<CalendarEvent[]>([])
const lastUpdated = ref<string>('')
const selectedMonday = ref<string>('')

function fmtYmd(d: Date): string {
  const yyyy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}`
}

function startOfDay(d: Date): Date {
  const x = new Date(d)
  x.setHours(0, 0, 0, 0)
  return x
}

function formatDisplayDate(ymd: string): string {
  // ymd is "YYYY-MM-DD"
  const [y, m, d] = ymd.split("-").map(Number);
  // Construct in local time
  const date = new Date(y, (m ?? 1) - 1, d ?? 1);

  return new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric"
  }).format(date);
}

function formatTime12h(isoDatetime: string): string {
  const date = new Date(isoDatetime);

  if (isNaN(date.getTime())) {
    return "";
  }

  const hours24 = date.getHours();
  const minutes = date.getMinutes();

  // Special cases
  if (hours24 === 0 && minutes === 0) return "midnight";
  if (hours24 === 12 && minutes === 0) return "noon";

  const period = hours24 < 12 ? "am" : "pm";
  const hours12 = hours24 % 12 === 0 ? 12 : hours24 % 12;

  // Omit minutes if exactly on the hour
  if (minutes === 0) {
    return `${hours12}${period}`;
  }

  const minuteStr = String(minutes).padStart(2, "0");
  return `${hours12}:${minuteStr}${period}`;
}

function nextMonday(from: Date): Date {
  const d = startOfDay(from)
  const day = d.getDay(); // 0=Sun..6=Sat
  const daysUntilMon = (8 - day) % 7; // Mon => 0, Sun => 1, Tue => 6
  d.setDate(d.getDate() + daysUntilMon)
  return d
}

function mondayOnOrBefore(d: Date): Date {
  const x = startOfDay(d)
  const day = x.getDay()
  const diffToMon = (day + 6) % 7; // Mon => 0, Tue => 1, Sun => 6
  x.setDate(x.getDate() - diffToMon)
  return x
}

const mondayOptions = computed<string[]>(() => {
  const today = new Date()
  const rangeStart = new Date(today)
  rangeStart.setMonth(rangeStart.getMonth() - 1)
  const rangeEnd = new Date(today)
  rangeEnd.setMonth(rangeEnd.getMonth() + 1)

  const firstMon = mondayOnOrBefore(rangeStart)
  const end = startOfDay(rangeEnd)
  const out: string[] = []
  for (let d = new Date(firstMon); d <= end; d.setDate(d.getDate() + 7)) {
    out.push(fmtYmd(d))
  }
  return out
})

function getStartDateFromUrl(): string | null {
  const url = new URL(window.location.href);
  const v = url.searchParams.get("start_date");
  // Expect YYYY-MM-DD
  if (!v || !/^\d{4}-\d{2}-\d{2}$/.test(v)) return null;
  return v;
}

function setStartDateInUrl(ymd: string): void {
  const url = new URL(window.location.href);
  url.searchParams.set("start_date", ymd);
  // Keep other params, update URL without a page reload
  window.history.replaceState({}, "", url.toString());
}

function pickInitialMonday(): string {
  const fromUrl = getStartDateFromUrl();
  const options = mondayOptions.value;

  // If URL has a valid option, honor it (persisted selection on reload)
  if (fromUrl && options.includes(fromUrl)) return fromUrl;

  // Default: next upcoming Monday (today if today is Monday)
  const fallback = fmtYmd(nextMonday(new Date()));
  return options.includes(fallback) ? fallback : (options[0] ?? fallback);
}

async function submitLogin(): Promise<void> {
  loggingIn.value = true;
  loginError.value = "";

  try {
    const basic = btoa(`${loginUser.value}:${loginPass.value}`);

    const res = await fetch('/api/login', {
      method: "POST",
      headers: {
        Authorization: `Basic ${basic}`,
        Accept: "application/json"
      },
      credentials: "include"
    });

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`Login failed: ${res.status}${text ? ` — ${text}` : ""}`);
    }

    isLoggedIn.value = true;

    // Immediately refresh your calendar data
    await initialize();

  } catch (e: unknown) {
    loginError.value = e instanceof Error ? e.message : String(e);
  } finally {
    loggingIn.value = false;
  }
}

async function fetchCalendar(): Promise<void> {
  loading.value = true
  error.value = ''

  try {
    const res = await fetch(`/api/calendar?start_date=${selectedMonday.value}`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      credentials: "include"
    })

    if (!res.ok) {
      const text = await res.text().catch(() => '')
      throw new Error(`HTTP ${res.status} ${res.statusText}${text ? ` — ${text}` : ''}`)
    }

    payload.value = (await res.json()) as CalendarEvent[]
    lastUpdated.value = new Date().toLocaleString()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
    payload.value = []
  } finally {
    loading.value = false
  }
}

const currentEditEventId = ref<number | null>(null)

const updating = ref<boolean>(false);
const updateError = ref<string | null>(null);
const updateOk = ref<boolean>(false);

const editedItemTitle = ref<string | null>(null);
const editedItemStartDatetime = ref<string | null>(null);
const editedItemVenue = ref<string | null>(null);
const editedItemNeighborhood = ref<string | null>(null);
const editedItemDescription = ref<string | null>(null);
const editedItemSourceUrl = ref<string | undefined>(undefined);
const editedItemSourceUrlProvider = ref<string | null>(null);
const editedItemMetadataDeleted = ref<boolean>(false);
const editedItemMetadataDone = ref<boolean>(false);
const editedItemMetadataIncoming = ref<boolean>(false);
const editedItemMetadataSupplemental = ref<boolean>(false);

const md = new MarkdownIt({ linkify: true, breaks: true });

function itemDescriptionHtml(itemDescriptionMarkdown: string): string {
  // sanitize HTML output before using v-html
  return DOMPurify.sanitize(md.renderInline(itemDescriptionMarkdown ?? ""));
}

const descriptionEditor = useEditor({
  extensions: [
    StarterKit,
    Link.configure({
      openOnClick: false,
      autolink: true,
      linkOnPaste: true,
    }),
   Markdown,
  ],
  content: "", // markdown
  editorProps: {
    attributes: {
      class: "mdEditor",
    },
  },
  onUpdate({ editor }) {
    // Persist as Markdown string
    editedItemDescription.value = editor.getMarkdown();
  }
});

watch(
  () => currentEditEventId.value,
  (eventId) => {

    const editor = descriptionEditor.value;
    if (!editor) return;

    // If user is editing, don't push content back down.
    if (editor.isFocused) return;

    if (eventId) {
      editor.commands.setContent(editedItemDescription.value || "", { contentType: "markdown" });
      editor.commands.focus("end");
    }
  }
);

onBeforeUnmount(() => {
  descriptionEditor.value?.destroy();
});

function setLink(): void {
  const editor = descriptionEditor.value;
  if (!editor) return;

  const prev = editor.getAttributes("link").href as string | undefined;
  const url = window.prompt("Link URL:", prev ?? "https://");
  if (!url) {
    editor.chain().focus().extendMarkRange("link").unsetLink().run();
    return;
  }
  editor.chain().focus().extendMarkRange("link").setLink({ href: url }).run();
}

function extractIsoTimezone(iso: string): string | null {
  const m = iso.match(/(Z|[+-]\d{2}:\d{2})$/);
  return m ? m[1] : null;
}

async function submitEditedItem(): Promise<void> {
  updating.value = true;
  updateError.value = '';
  updateOk.value = false;

  const currentEvent = payload.value.find(event => event.grist_record_id === currentEditEventId.value)
  if (!currentEvent) {
    updating.value = false
    return
  }

  try {
    const body: CalendarEvent = {
      title: editedItemTitle.value || null,
      start_datetime: editedItemStartDatetime.value || '' + extractIsoTimezone(currentEvent.start_datetime),
      description: editedItemDescription.value || null,
      source_url: editedItemSourceUrl.value,
      source_url_provider: editedItemSourceUrlProvider.value || null,
      location: {
        venue: editedItemVenue.value || null,
        neighborhood: editedItemNeighborhood.value || null
      },
      calendar_metadata: {
        deleted: editedItemMetadataDeleted.value || false,
        done: editedItemMetadataDone.value || false,
        incoming: editedItemMetadataIncoming.value || false,
        supplemental: editedItemMetadataSupplemental.value || false,
      }
    };

    const res = await fetch(`/api/calendar/update/${currentEditEventId.value}`, {
      method: 'POST',
      headers: {
        "Content-Type": "application/json",
        Accept: 'application/json',
        credentials: "include"
      },
      body: JSON.stringify(body),
    })

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status} ${res.statusText}${text ? ` — ${text}` : ""}`);
    }

    resetUpdateForm()
    currentEditEventId.value = null
    await fetchCalendar()
    lastUpdated.value = new Date().toLocaleString()

  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
    payload.value = []

  } finally {
    updating.value = false
  }
}

function setCurrentEditEvent(event: CalendarEvent): void {
  currentEditEventId.value = event.grist_record_id || null
  editedItemTitle.value = event.title || null
  editedItemStartDatetime.value = event.start_datetime.slice(0, 16) || null
  editedItemVenue.value = event.location?.venue || null
  editedItemNeighborhood.value = (event.location && (event.location.neighborhood || event.location.city)) || 'Oakland'
  editedItemDescription.value = event.description || null
  editedItemSourceUrl.value = event.source_url
  editedItemSourceUrlProvider.value = event.source_url_provider || event.organizer?.name || event.source_url || null
  editedItemMetadataDeleted.value = event.calendar_metadata?.deleted || false;
  editedItemMetadataDone.value = event.calendar_metadata?.done || false;
  editedItemMetadataIncoming.value = event.calendar_metadata?.incoming || false;
  editedItemMetadataSupplemental.value = event.calendar_metadata?.supplemental || false;
  updateError.value = null
  updateOk.value = false
}

function resetUpdateForm(): void {
  editedItemTitle.value = null;
  editedItemStartDatetime.value = null;
  editedItemVenue.value = null;
  editedItemNeighborhood.value = null;
  editedItemDescription.value = null;
  editedItemSourceUrl.value = undefined;
  editedItemSourceUrlProvider.value = null;
  editedItemMetadataDeleted.value = false;
  editedItemMetadataDone.value = false;
  editedItemMetadataIncoming.value = false;
  editedItemMetadataSupplemental.value = false;
  updateError.value = null;
  updateOk.value = false;
}

function onCancelUpdate(): void {
  resetUpdateForm
  currentEditEventId.value = null
}

const groupedByDateAndSupplemental = computed<Record<string, Record<`${boolean}`, CalendarEvent[]>>>(() => {
  const items = payload.value ?? []
  const out: Record<string, Record<`${boolean}`, CalendarEvent[]>> = {}

  for (const item of items) {
    const iso = item?.start_datetime;
    if (typeof iso !== 'string') continue;
    // Date portion of ISO 8601: "YYYY-MM-DD"
    const dateKey = iso.slice(0, 10)
    const supplementalKey: boolean = item?.calendar_metadata?.supplemental || false
    if (!out[dateKey]) out[dateKey] = {true: [], false: []}
    out[dateKey][`${supplementalKey}`].push(item)
  }

  // Stable ordering by date key
  return Object.fromEntries(Object.entries(out).sort(([a], [b]) => a.localeCompare(b)));
})

async function initialize(): Promise<void> {
  // Initialize from URL (if present), otherwise default to next upcoming Monday.
  selectedMonday.value = pickInitialMonday();
  // Ensure URL reflects the initialized selection.
  setStartDateInUrl(selectedMonday.value);
  await fetchCalendar();
}

async function checkSession(): Promise<void> {
  try {
    const res = await fetch('/api/me', {
      credentials: "include"
    });
    if (res.ok) {
      isLoggedIn.value = true
      await initialize()
    }
  } catch {
    /* ignore */
  }
}

onMounted(() => {
  checkSession()
})

// Auto-fetch whenever the week changes
watch(selectedMonday, () => {
  // Persist selection in the URL and make it shareable/bookmarkable.
  setStartDateInUrl(selectedMonday.value);
  void fetchCalendar()
})
</script>

<style>
:root {
  color-scheme: light dark;
  --maxw: 900px;
  --pad: 18px;
  --border: rgba(127, 127, 127, 0.35);
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial,
    "Apple Color Emoji", "Segoe UI Emoji";
  line-height: 1.4;
}

.wrap {
  max-width: var(--maxw);
  margin: 0 auto;
  padding: 28px var(--pad);
}

.header h1 {
  margin: 0 0 6px 0;
  font-size: 28px;
}

.sub {
  margin: 0;
  opacity: 0.8;
}

.controls {
  display: flex;
  align-items: center;
  gap: 14px;
  margin: 18px 0;
  flex-wrap: wrap;
}

.label {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 6px 10px;
}

.label > span {
  opacity: 0.85;
  font-size: 14px;
}

.select {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: transparent;
  padding: 6px 8px;
  cursor: pointer;
}

.btn {
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: transparent;
  cursor: pointer;
  display: block;
}

.btn-edit-full {
  margin-top: 10px;
}

.btn-inline {
  display: inline;
  margin-right: 5px;
  padding: 4px;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.meta {
  opacity: 0.75;
  font-size: 14px;
}

.error {
  border: 1px solid rgba(255, 0, 0, 0.35);
  border-radius: 12px;
  padding: 12px 14px;
  margin: 10px 0 16px 0;
}

.panel {
  border: 1px solid var(--border);
  border-radius: 14px;
  overflow: hidden;
  padding: 10px;
}

.pre {
  margin: 0;
  padding: 14px;
  overflow: auto;
  min-height: 220px;
  font-size: 13px;
}

.formPanel {
  margin-top: 16px;
  padding: 14px;
}

.formHeader {
  margin-bottom: 10px;
}

.h2 {
  margin: 0 0 6px 0;
  font-size: 18px;
}

.muted {
  margin: 0;
  opacity: 0.75;
}

.form {
  display: grid;
  gap: 12px;
}

.field {
  display: grid;
  gap: 6px;
}

.fieldLabel {
  font-size: 14px;
  opacity: 0.85;
}

.input,
.textarea,
.select {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: transparent;
  padding: 8px 10px;
  font: inherit;
}

.help {
  font-size: 12px;
  opacity: 0.7;
}

.formActions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.ok {
  opacity: 0.85;
}

.checkboxLabel {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
}

.errorInline {
  color: inherit;
  opacity: 0.9;
}

.text-done {
  color: #000;
}

.text-not-done {
  color: #888;
}

.mdWrap {
  display: grid;
  gap: 10px;
}

.mdToolbar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.mdEditor {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 0 12px;
  min-height: 120px;
}

.mdEditor:focus {
  outline: none;
}

.mdPreview {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  min-height: 60px;
}

.mdPreview :where(p) {
  margin: 0.4em 0;
}

.mdPreview :where(a) {
  text-decoration: underline;
}
</style>
