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
      <div v-if="Object.keys(groupedByDate).length === 0" class="empty">
        No data yet.
      </div>
      <div v-for="(events, date) in groupedByDate" :key="date" class="day">
        <p>
          <strong><u>{{ formatDisplayDate(date) }}</u></strong>
        </p>
        <div v-for="event in events">
          <p v-if="event.grist_record_id !== currentEditEventId">
            <strong>
              {{event.title}}
            </strong>,
            {{ formatTime12h(event.start_datetime) }},
            {{ event.location?.venue }}
            ({{ event.location?.neighborhood || event.location?.city || 'Oakland'}}).
            {{ event.description }}
            [<a :href="event.source_url">{{event.source_url_provider || event.organizer?.name || event.source_url}}</a>]
            <button
              v-if="allowEdits && !currentEditEventId"
              class="btn"
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
                <textarea
                  class="textarea"
                  v-model="editedItemDescription"
                  rows="8"
                />
              </label>

              <label class="field">
                <span class="fieldLabel">URL</span>
                <input class="input" type="text" v-model="editedItemSourceUrl" />
              </label>

              <label class="field">
                <span class="fieldLabel">URL Provider</span>
                <input class="input" type="text" v-model="editedItemSourceUrlProvider" />
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
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

type CalendarLocation = {
  city?: string | null,
  venue?: string | null,
  neighborhood?: string | null,
  [key: string]: unknown
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
  updateError.value = null;
  updateOk.value = false;
}

function onCancelUpdate(): void {
  resetUpdateForm
  currentEditEventId.value = null
}

const groupedByDate = computed<Record<string, CalendarEvent[]>>(() => {
  const items = payload.value ?? []
  const out: Record<string, CalendarEvent[]> = {}

  for (const item of items) {
    const iso = item?.start_datetime;
    if (typeof iso !== 'string') continue;
    // Date portion of ISO 8601: "YYYY-MM-DD"
    const dateKey = iso.slice(0, 10)
    if (!out[dateKey]) out[dateKey] = []
    out[dateKey].push(item)
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
</style>
