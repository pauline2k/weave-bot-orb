<template>
  <main class="wrap">
    <header class="header">
      <h1>🔮 Oakland Review of Books calendar of (not just) literary events</h1>
    </header>

    <section class="controls">
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
    </section>

    <section v-if="error" class="error">
      <strong>Error:</strong> {{ error }}
    </section>

    <section class="panel">
      <div v-if="Object.keys(groupedByDate).length === 0" class="empty">
        No data yet.
      </div>
      <div v-for="(events, date) in groupedByDate" :key="date" class="day">
        <p>
          <strong><u>{{ formatDisplayDate(date) }}</u></strong>
        </p>
        <p v-for="event in events">
          <strong>
            {{event.title}}
          </strong>,
          {{ formatTime12h(event.start_datetime) }},
          {{ event.location?.venue }}
          ({{ event.location?.city || 'Oakland'}}).
          {{ event.description }}
          [<a :href="event.source_url">{{event.organizer?.name || event.source_url}}</a>]
        </p>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

type CalendarLocation = {
  city?: string,
  venue?: string,
  [key: string]: unknown
}

type CalendarOrganizer = {
  name?: string,
}

type CalendarEvent = {
  start_datetime: string // ISO 8601 datetime,
  source_url?: string,
  location?: CalendarLocation,
  organizer?: CalendarOrganizer,
  // Other properties exist but are not relevant here.
  [key: string]: unknown
}



const loading = ref<boolean>(false)
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

const apiBaseUrl = import.meta.env.VITE_APP_API_BASE_URL

async function fetchCalendar(): Promise<void> {
  loading.value = true
  error.value = ''

  try {
    const res = await fetch(`${apiBaseUrl}/api/calendar?start_date=${selectedMonday.value}`, {
      method: 'GET',
      headers: { Accept: 'application/json' }
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

onMounted(() => {
  // Initialize from URL (if present), otherwise default to next upcoming Monday.
  selectedMonday.value = pickInitialMonday();
  // Ensure URL reflects the initialized selection.
  setStartDateInUrl(selectedMonday.value);
  void fetchCalendar();
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
</style>
