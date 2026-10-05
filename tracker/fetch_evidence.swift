// Fast Evidence. calendar pull via EventKit (replaces the slow Calendar.app
// AppleScript whose-filter, ~90s → ~0.3s). Prints TSV: start<TAB>end<TAB>summary
// in SYSTEM-LOCAL time (build_data.py converts local → canonical timezone).
//
// Build:  swiftc -O fetch_evidence.swift -o fetch_evidence
// (refresh.sh compiles automatically if the binary is missing or stale.)
import EventKit
import Foundation

// ============================ CONFIG ============================
// Name of the macOS/iCloud calendar that holds the "what actually happened"
// events. Must match exactly (create it in Calendar.app first). The trailing
// period in the original ("Evidence.") is just a naming choice — use anything.
let CALENDAR_NAME = "Evidence."
// Earliest date to pull (year, month, day). Set to when you started tracking.
let PULL_FROM = (year: 2026, month: 1, day: 1)
// ===============================================================

let store = EKEventStore()
let sem = DispatchSemaphore(value: 0)
var granted = false
if #available(macOS 14.0, *) {
    store.requestFullAccessToEvents { ok, _ in granted = ok; sem.signal() }
} else {
    store.requestAccess(to: .event) { ok, _ in granted = ok; sem.signal() }
}
sem.wait()
guard granted else {
    FileHandle.standardError.write("NO_CALENDAR_ACCESS\n".data(using: .utf8)!)
    exit(2)
}

let cals = store.calendars(for: .event).filter { $0.title == CALENDAR_NAME }
guard !cals.isEmpty else {
    FileHandle.standardError.write("NO_EVIDENCE_CAL\n".data(using: .utf8)!)
    exit(3)
}

let fmt = DateFormatter()
fmt.dateFormat = "yyyy-MM-dd HH:mm:ss"

var c = DateComponents(); c.year = PULL_FROM.year; c.month = PULL_FROM.month; c.day = PULL_FROM.day
let start = Calendar.current.date(from: c)!
let end = Date().addingTimeInterval(86400)

// EventKit predicates span at most ~4 years; this window is fine.
let pred = store.predicateForEvents(withStart: start, end: end, calendars: cals)
for e in store.events(matching: pred) {
    let title = (e.title ?? "").replacingOccurrences(of: "\t", with: " ")
    print("\(fmt.string(from: e.startDate))\t\(fmt.string(from: e.endDate))\t\(title)")
}
