// fifa19.toml edited in place: only the top-level `key = value` lines the launcher sets change or are added;
// comments, tables, other keys and their order stay. A key set back to its default is removed, so the file
// holds only what was changed. Only single-line strings, integers, floats and booleans are read.

import Foundation

enum TomlValue: Equatable {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)

    var literal: String {
        switch self {
        case .string(let s):
            var out = "\""
            for c in s.unicodeScalars {
                switch c {
                case "\\": out += "\\\\"
                case "\"": out += "\\\""
                case "\n": out += "\\n"
                case "\t": out += "\\t"
                default:
                    if c.value < 0x20 { out += String(format: "\\u%04X", c.value) } else { out.unicodeScalars.append(c) }
                }
            }
            return out + "\""
        case .int(let i): return String(i)
        case .double(let d): return d == d.rounded() && abs(d) < 1e15 ? String(format: "%.1f", d) : String(d)
        case .bool(let b): return b ? "true" : "false"
        }
    }

    var string: String? { if case .string(let s) = self { return s }; return nil }
    var bool: Bool? { if case .bool(let b) = self { return b }; return nil }
    var number: Double? {
        switch self {
        case .int(let i): return Double(i)
        case .double(let d): return d
        default: return nil
        }
    }
    var int: Int? {
        switch self {
        case .int(let i): return i
        case .double(let d): return Int(d)
        default: return nil
        }
    }

    /// Parses the value at the start of `text` (after `key =`); nil for anything the launcher doesn't write.
    static func parse(_ text: Substring) -> TomlValue? {
        let t = text.trimmingCharacters(in: .whitespaces)
        if t.hasPrefix("\"") {
            var out = "", escaped = false
            for c in t.dropFirst() {
                if escaped {
                    switch c {
                    case "n": out.append("\n")
                    case "t": out.append("\t")
                    default: out.append(c)
                    }
                    escaped = false
                } else if c == "\\" {
                    escaped = true
                } else if c == "\"" {
                    return .string(out)
                } else {
                    out.append(c)
                }
            }
            return nil
        }
        let bare = t.split(separator: "#", maxSplits: 1).first.map { $0.trimmingCharacters(in: .whitespaces) } ?? ""
        if bare == "true" { return .bool(true) }
        if bare == "false" { return .bool(false) }
        if let i = Int(bare) { return .int(i) }
        if let d = Double(bare) { return .double(d) }
        return nil
    }
}

struct TomlFile {
    private(set) var lines: [String]

    init(text: String) { lines = text.isEmpty ? [] : text.components(separatedBy: "\n") }

    var text: String { lines.joined(separator: "\n") }

    /// Top-level statements: the lines before the first [table] header.
    private func topLevel() -> [(key: String, line: Int, value: Substring)] {
        var out: [(String, Int, Substring)] = []
        for (i, line) in lines.enumerated() {
            let t = line.trimmingCharacters(in: .whitespaces)
            if t.hasPrefix("[") { break }
            if t.isEmpty || t.hasPrefix("#") { continue }
            guard let eq = line.firstIndex(of: "=") else { continue }
            let key = line[..<eq].trimmingCharacters(in: .whitespaces)
            out.append((key, i, line[line.index(after: eq)...]))
        }
        return out
    }

    func value(_ key: String) -> TomlValue? {
        topLevel().last { $0.key == key }.flatMap { TomlValue.parse($0.value) }
    }

    mutating func set(_ key: String, _ value: TomlValue?) {
        let found = topLevel().filter { $0.key == key }
        guard let value else {
            for entry in found.reversed() { lines.remove(at: entry.line) }
            return
        }
        let line = "\(key) = \(value.literal)"
        if let last = found.last {
            lines[last.line] = line
            return
        }
        // New keys go after the last top-level statement (before any table), or at the end.
        let insertAt = (topLevel().last?.line).map { $0 + 1 } ?? (lines.firstIndex { $0.hasPrefix("[") } ?? lines.count)
        lines.insert(line, at: insertAt)
    }
}
