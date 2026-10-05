// Fast EventKit writer for the work calendars — no Calendar.app scripting needed.
// Reads a JSON array of ops from stdin, applies them, commits once.
//
//   create: {"op":"create","start":"2026-01-18 17:30","end":"2026-01-18 18:00","summary":"★★★ deep work"}
//   update: {"op":"update","start":"2026-01-18 17:30","match":"★★★ deep work","end":"2026-01-18 18:15","summary":"★★★★ deep work"}
//           (find by start+match; set end and/or summary if provided)
//   delete: {"op":"delete","start":"2026-01-18 17:30","match":"rest (break)"}
//
//   Optional per-op "cal": targets a calendar by title. Default = DEFAULT_CAL below
//   (the "what happened" calendar). Use a second calendar (e.g. "Intention") for plans.
//   Times are written in the machine's LOCAL timezone. Build: swiftc -O calwrite.swift -o calwrite
import EventKit
import Foundation

// Default calendar title for writes (must match fetch_evidence.swift's CALENDAR_NAME).
let DEFAULT_CAL = "Evidence."

let store = EKEventStore()
let sem = DispatchSemaphore(value: 0)
var granted = false
if #available(macOS 14.0, *) { store.requestFullAccessToEvents { ok, _ in granted = ok; sem.signal() } }
else { store.requestAccess(to: .event) { ok, _ in granted = ok; sem.signal() } }
sem.wait()
guard granted else { FileHandle.standardError.write("NO_CALENDAR_ACCESS\n".data(using:.utf8)!); exit(2) }

// Resolve calendars by title; default target is "Evidence."
var calsByTitle: [String: EKCalendar] = [:]
for c in store.calendars(for: .event) { calsByTitle[c.title] = c }
guard let _ = calsByTitle[DEFAULT_CAL] else { FileHandle.standardError.write("NO_DEFAULT_CAL\n".data(using:.utf8)!); exit(3) }
func calFor(_ op: [String: Any]) -> EKCalendar? {
    let title = (op["cal"] as? String) ?? DEFAULT_CAL
    return calsByTitle[title]
}

let df = DateFormatter()
df.dateFormat = "yyyy-MM-dd HH:mm"
df.timeZone = TimeZone.current
func parse(_ s: String?) -> Date? { guard let s = s else { return nil }; return df.date(from: s) }

let data = FileHandle.standardInput.readDataToEndOfFile()
guard let ops = (try? JSONSerialization.jsonObject(with: data)) as? [[String: Any]] else {
    FileHandle.standardError.write("BAD_JSON\n".data(using:.utf8)!); exit(4)
}

// helper: find events on `cal` starting exactly at `start`
func find(start: Date, match: String?, cal: EKCalendar) -> [EKEvent] {
    let pred = store.predicateForEvents(withStart: start.addingTimeInterval(-60),
                                        end: start.addingTimeInterval(60), calendars: [cal])
    return store.events(matching: pred).filter {
        abs($0.startDate.timeIntervalSince(start)) < 30 && (match == nil || $0.title == match!)
    }
}

var created = 0, updated = 0, deleted = 0, errors = 0
for op in ops {
    let kind = op["op"] as? String ?? ""
    guard let start = parse(op["start"] as? String) else { errors += 1; continue }
    guard let cal = calFor(op) else { FileHandle.standardError.write("NO_CAL:\((op["cal"] as? String) ?? "?")\n".data(using:.utf8)!); errors += 1; continue }
    if kind == "create" {
        guard let end = parse(op["end"] as? String), let summ = op["summary"] as? String else { errors += 1; continue }
        let ev = EKEvent(eventStore: store)
        ev.calendar = cal; ev.title = summ; ev.startDate = start; ev.endDate = end
        do { try store.save(ev, span: .thisEvent, commit: false); created += 1 } catch { errors += 1 }
    } else if kind == "update" {
        let matches = find(start: start, match: op["match"] as? String, cal: cal)
        for ev in matches {
            if let end = parse(op["end"] as? String) { ev.endDate = end }
            if let summ = op["summary"] as? String { ev.title = summ }
            do { try store.save(ev, span: .thisEvent, commit: false); updated += 1 } catch { errors += 1 }
        }
    } else if kind == "delete" {
        for ev in find(start: start, match: op["match"] as? String, cal: cal) {
            do { try store.remove(ev, span: .thisEvent, commit: false); deleted += 1 } catch { errors += 1 }
        }
    }
}
do { try store.commit() } catch { FileHandle.standardError.write("COMMIT_FAIL\n".data(using:.utf8)!); exit(5) }
print("created \(created), updated \(updated), deleted \(deleted), errors \(errors)")
